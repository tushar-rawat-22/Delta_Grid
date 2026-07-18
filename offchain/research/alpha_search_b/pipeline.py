from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import AUTHORIZED_SYMBOLS, PROTOCOL_HASH
from .engine import (
    CANDIDATES, build_features, development_gates, holm_adjust, metrics,
    null_control, quantity_step, select_candidate, simulate, trade_dicts,
)
from .foundation import (
    COST_PATH, DATA_ROOT, ROOT, PublicDownloader, assert_preflight_storage,
    authorized_months, canonical_hash, iter_certified_zip, load_cost_attribution,
    load_json, sha256_file, verify_protocol,
)

RAW_DIR = DATA_ROOT / "raw"
PROCESSED_DIR = DATA_ROOT / "processed"
ARTIFACT_DIR = DATA_ROOT / "artifacts"
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "alpha_search_b_development"
BASE_COMMIT = "27287ef1cf1bcfb7ded91e68c72b51306a97fab5"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")


def acquire() -> None:
    verify_protocol(); load_cost_attribution(); assert_preflight_storage()
    RAW_DIR.mkdir(parents=True,exist_ok=True)
    jobs=[(symbol,month) for symbol in AUTHORIZED_SYMBOLS for month in authorized_months()]
    def job(item: tuple[str,str]) -> tuple[dict[str,Any],dict[str,int]]:
        downloader=PublicDownloader()
        return downloader.download_pair_month(*item,RAW_DIR),downloader.counters
    records=[]; counters=Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for record,counts in pool.map(job,jobs): records.append(record); counters.update(counts)
    api=PublicDownloader(); snapshot=api.exchange_snapshot(); counters.update(api.counters)
    write_json(RAW_DIR/"exchange_snapshot.json",snapshot)
    write_json(DATA_ROOT/"acquisition.json",{
        "expected_archive_count":75,"pair_month_coverage":{"pairs":list(AUTHORIZED_SYMBOLS),"months":list(authorized_months())},
        "bounded_download_concurrency":4,"archives":sorted(records,key=lambda x:(x["symbol"],x["month"])),
        "exchange_snapshot":snapshot,"prohibited_access_counters":dict(counters),
    })


def certify() -> None:
    acquisition=load_json(DATA_ROOT/"acquisition.json")
    PROCESSED_DIR.mkdir(parents=True,exist_ok=True)
    reports=[]
    for archive in acquisition["archives"]:
        path=ROOT/archive["archive_path"]; rows=[]; units=Counter(); timestamps=[]
        for row in iter_certified_zip(path,path.name):
            record=asdict(row); units[row.timestamp_unit]+=1; timestamps.append(row.open_time_ms); rows.append(record)
        month=archive["month"]
        start=int(pd.Timestamp(f"{month}-01",tz="UTC").timestamp()*1000)
        end=int((pd.Timestamp(f"{month}-01",tz="UTC")+pd.offsets.MonthBegin(1)).timestamp()*1000)
        expected=np.arange(start,end,60_000,dtype=np.int64)
        observed=np.asarray(timestamps,dtype=np.int64)
        if len(observed) and (observed[0]<start or observed[-1]>=end):
            raise RuntimeError("ALPHA_SEARCH_B_ARCHIVE_MONTH_COVERAGE_INVALID")
        missing=np.setdiff1d(expected,observed,assume_unique=True)
        gap_intervals=[]
        if len(missing):
            interval_start=interval_end=int(missing[0])
            for value in missing[1:]:
                value=int(value)
                if value==interval_end+60_000: interval_end=value
                else:
                    gap_intervals.append({"start_open_time_ms":interval_start,"end_open_time_ms":interval_end,
                        "missing_minutes":1+(interval_end-interval_start)//60_000})
                    interval_start=interval_end=value
            gap_intervals.append({"start_open_time_ms":interval_start,"end_open_time_ms":interval_end,
                "missing_minutes":1+(interval_end-interval_start)//60_000})
        output=PROCESSED_DIR/f"{archive['symbol']}-1m-{month}.parquet"
        table=pa.Table.from_pylist(rows)
        pq.write_table(table,output,compression="zstd")
        reports.append({"symbol":archive["symbol"],"month":month,"row_count":len(rows),
            "expected_rows":len(expected),"gap_count":len(missing),"duplicate_count":0,
            "gap_intervals":gap_intervals,
            "timestamp_unit_counts":dict(units),"first_open_time_ms":int(observed[0]),"last_open_time_ms":int(observed[-1]),
            "processed_path":str(output.relative_to(ROOT)),"processed_sha256":sha256_file(output)})
    write_json(DATA_ROOT/"certification.json",{"status":"PASS","pair_month_count":len(reports),
        "schema":["open_time_ms","open","high","low","close","volume","close_time_ms",
            "quote_asset_volume","number_of_trades","taker_buy_base_asset_volume",
            "taker_buy_quote_asset_volume","timestamp_unit"],
        "reports":reports,"total_gaps":sum(x["gap_count"] for x in reports),"total_duplicates":0})


def load_frames() -> dict[str,pd.DataFrame]:
    start=pd.Timestamp("2022-06-01",tz="UTC"); end=pd.Timestamp("2024-07-01",tz="UTC")
    grid=np.arange(int(start.timestamp()*1000),int(end.timestamp()*1000),60_000,dtype=np.int64)
    frames={}
    for symbol in AUTHORIZED_SYMBOLS:
        paths=[PROCESSED_DIR/f"{symbol}-1m-{month}.parquet" for month in authorized_months()]
        frame=pd.concat((pd.read_parquet(path) for path in paths),ignore_index=True)
        frame=frame.set_index("open_time_ms").reindex(grid); frame.index.name="open_time_ms"
        frame["complete"]=frame["open"].notna(); frame=frame.reset_index()
        frames[symbol]=frame
    return frames


def replication_signals(candidate: str, features: Mapping[str,Any]) -> dict[str,np.ndarray]:
    pair,_,kind=CANDIDATES[candidate]
    if kind=="SELF":
        return {symbol:np.flatnonzero(features["self_flags"][symbol]) for symbol in ("ETHUSDT","SOLUSDT")}
    target="SOLUSDT" if pair=="ETHUSDT" else "ETHUSDT"
    other=f"BTC_FLOW_LEADS_{target.removesuffix('USDT')}_60M"
    return {target:np.flatnonzero(features["signals"][other])}


def run() -> None:
    protocol=verify_protocol(); costs=load_cost_attribution(); frames=load_frames()
    snapshot=load_json(DATA_ROOT/"acquisition.json")["exchange_snapshot"]
    features=build_features(frames)
    ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
    all_results={}; replication_results={}; simulations={}; null_summaries={}; raw_p={}
    for candidate,(pair,holding,_) in CANDIDATES.items():
        signal_indices=np.flatnonzero(features["signals"][candidate])
        step=quantity_step(snapshot,pair); scenario_metrics={}; simulations[candidate]={}
        for scenario in ("normal","conservative","severe"):
            sim=simulate(candidate,signal_indices,frames[pair],scenario,costs["components_bps"][pair][scenario],step)
            simulations[candidate][scenario]=sim
        normal_gross={trade.signal_timestamp:Decimal(trade.gross_dollar_pnl) for trade in simulations[candidate]["normal"].trades}
        for scenario,sim in simulations[candidate].items():
            for trade in sim.trades:
                if trade.signal_timestamp in normal_gross:
                    trade.latency_displacement_diagnostic=str(normal_gross[trade.signal_timestamp]-Decimal(trade.gross_dollar_pnl))
            scenario_metrics[scenario]=metrics(sim)
            ledger=ARTIFACT_DIR/f"{candidate}-{scenario}-ledger.json"
            write_json(ledger,trade_dicts(sim))
            scenario_metrics[scenario]["ledger_sha256"]=sha256_file(ledger)
        reps={}
        for rep_pair,indices in replication_signals(candidate,features).items():
            rep=simulate(candidate,indices,frames[rep_pair],"conservative",costs["components_bps"][rep_pair]["conservative"],
                quantity_step(snapshot,rep_pair),pair_override=rep_pair,holding_override=holding)
            reps[rep_pair]=metrics(rep)
            rep_ledger=ARTIFACT_DIR/f"{candidate}-replication-{rep_pair}-conservative-ledger.json"
            write_json(rep_ledger,trade_dicts(rep)); reps[rep_pair]["ledger_sha256"]=sha256_file(rep_ledger)
        replication_results[candidate]=reps
        rep_pass=any(row["trade_count"]>=120 and Decimal(row["net_profit"])>0 for row in reps.values())
        observed=simulations[candidate]["conservative"]
        vector,summary=null_control(candidate,observed,np.flatnonzero(features["eligibility"][candidate]),frames[pair],
            costs["components_bps"][pair]["conservative"],step)
        placebo_path=ARTIFACT_DIR/f"{candidate}-placebo.npy"; np.save(placebo_path,vector,allow_pickle=False)
        summary["placebo_sha256"]=sha256_file(placebo_path); null_summaries[candidate]=summary; raw_p[candidate]=summary["raw_p_value"]
        all_results[candidate]={"signal_attempt_count":len(signal_indices),"metrics":scenario_metrics,"replication_pass":rep_pass}
    adjusted=holm_adjust(raw_p)
    for candidate,row in all_results.items():
        row["holm_adjusted_p_value"]=adjusted[candidate]
        row["gates"]=development_gates(row["metrics"]["normal"],row["metrics"]["conservative"],row["replication_pass"],adjusted[candidate])
    selected=select_candidate(all_results)
    decision="ALPHA_SEARCH_B_DEVELOPMENT_SURVIVOR_SELECTED" if selected else "ALPHA_SEARCH_B_REJECTED_DEVELOPMENT"
    write_json(DATA_ROOT/"run_results.json",{"protocol_hash":PROTOCOL_HASH,"candidate_results":all_results,
        "replication_results":replication_results,"null_control":null_summaries,"holm_adjusted":adjusted,
        "decision":decision,"selected_candidate":selected})
    evidence(protocol,costs,all_results,replication_results,null_summaries,adjusted,decision,selected)


def evidence(protocol: Mapping[str,Any],costs: Mapping[str,Any],results: Mapping[str,Any],replications: Mapping[str,Any],
             nulls: Mapping[str,Any],adjusted: Mapping[str,float],decision: str,selected: str|None) -> None:
    acquisition=load_json(DATA_ROOT/"acquisition.json"); certification=load_json(DATA_ROOT/"certification.json")
    EVIDENCE_DIR.mkdir(parents=True,exist_ok=True)
    write_json(EVIDENCE_DIR/"COST_ATTRIBUTION.json",{"contract_sha256":sha256_file(COST_PATH),"contract":costs})
    write_json(EVIDENCE_DIR/"DATA_ACQUISITION_MANIFEST.json",{"base_git_commit":BASE_COMMIT,"protocol_hash":PROTOCOL_HASH,
        "expected_archive_count":75,"archives":acquisition["archives"],"exchange_snapshot":acquisition["exchange_snapshot"]})
    write_json(EVIDENCE_DIR/"DATA_CERTIFICATION.json",certification)
    implementation={str(path.relative_to(ROOT)):sha256_file(path) for path in sorted((ROOT/"offchain/research/alpha_search_b").glob("*.py"))}
    write_json(EVIDENCE_DIR/"FEATURE_ENGINE_MANIFEST.json",{"protocol_hash":PROTOCOL_HASH,"window":43200,"minimum_observations":38880,
        "quantile":"NEAREST_RANK_EMPIRICAL","causal_current_excluded":True,"implementation_hashes":implementation})
    write_json(EVIDENCE_DIR/"SIMULATOR_MANIFEST.json",{"scenarios":{"normal":1,"conservative":2,"severe":3},"stop_rate":"0.015",
        "cooldown_minutes":1440,"decimal_accounting":True,"implementation_hashes":implementation})
    write_json(EVIDENCE_DIR/"CANDIDATE_DEVELOPMENT_RESULTS.json",results)
    write_json(EVIDENCE_DIR/"REPLICATION_RESULTS.json",replications)
    write_json(EVIDENCE_DIR/"NULL_CONTROL_RESULTS.json",nulls)
    write_json(EVIDENCE_DIR/"HOLM_ADJUSTMENT.json",{"family_size":4,"adjusted_p_values":adjusted})
    write_json(EVIDENCE_DIR/"PNL_ATTRIBUTION.json",{key:row["metrics"] for key,row in results.items()})
    audit=acquisition["prohibited_access_counters"]
    write_json(EVIDENCE_DIR/"PROHIBITED_ACCESS_AUDIT.json",audit)
    next_action="ALPHA_SEARCH_B_VALIDATION_DATA_AND_FIXED_CANDIDATE_EVALUATION" if selected else "FREEZE_DELTAGRID_AS_COMPLETED_RESEARCH_PLATFORM"
    decision_record={"decision":decision,"selected_candidate":selected,"protocol_hash":PROTOCOL_HASH,
        "development_only":True,"validation_performance_accessed":False,"holdout_performance_accessed":False,
        "freqtrade_translation":False,"dry_run":False,"live_trading":False,"capital_deployment":False,"next_action":next_action}
    write_json(EVIDENCE_DIR/"DEVELOPMENT_DECISION.json",decision_record)
    (EVIDENCE_DIR/"DEVELOPMENT_DECISION.md").write_text(
        f"# Alpha Search B Development Decision\n\nDecision: `{decision}`\n\nSelected candidate: `{selected}`\n\n"
        f"Development data only. Validation and holdout remain sealed.\n\nNext action: `{next_action}`\n",encoding="utf-8")
    hashes=[]
    for path in sorted(EVIDENCE_DIR.iterdir()):
        if path.name!="SHA256SUMS.txt": hashes.append(f"{sha256_file(path)}  {path.name}")
    (EVIDENCE_DIR/"SHA256SUMS.txt").write_text("\n".join(hashes)+"\n",encoding="utf-8")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("phase",choices=("acquire","certify","run")); args=parser.parse_args()
    {"acquire":acquire,"certify":certify,"run":run}[args.phase]()


if __name__=="__main__": main()
