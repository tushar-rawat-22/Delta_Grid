# Statistical integrity diagnostics

DeltaGrid treats backtest performance as a research claim, not as proof of an investable edge. Repeated strategy search, non-normal returns, and selection of the best-looking result can inflate an ordinary Sharpe ratio even when the underlying evidence is weak.

`offchain/research/statistical_integrity.py` adds a diagnostic-only layer for that failure mode. It computes sample skewness and kurtosis, period and annualized Sharpe, the Probabilistic Sharpe Ratio (PSR), the expected best Sharpe implied by the observed spread and count of research trials, and the Deflated Sharpe Ratio (DSR). It also reports lag-1 autocorrelation as a dependence warning.

These diagnostics do not alter any existing admission gate, candidate-selection rule, research authorization, paper-trading authority, exchange authority, or capital authority. They are evidence for reviewers. They are not a permission surface.

## Interpretation limits

PSR/DSR correct for non-normality and search/selection effects under their stated assumptions. This implementation does not claim to correct serial dependence. The report therefore sets `serial_dependence_adjusted` to `false` and exposes lag-1 autocorrelation rather than hiding the limitation. Dependence-aware resampling is a separate research-integrity problem and should be handled explicitly rather than folded into an unjustified Sharpe adjustment.

Insufficient observations and zero-variance returns do not produce synthetic zero scores. They return explicit non-result statuses and leave the inferential fields unset.

## References

The implementation follows the statistical framing in Bailey and Lopez de Prado, “The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality,” Journal of Portfolio Management 40(5), 2014. DeltaGrid's existing Alpha Search B controls already add Holm family-wise correction and stratified Monte Carlo null testing; this module is complementary rather than a replacement for those controls.
