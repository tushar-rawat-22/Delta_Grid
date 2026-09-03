import type { Metadata } from "next";
import { PublicResearchDemo } from "../../components/public-research-demo";

export const metadata: Metadata = {
  title: "Research Demo",
  description: "Explore DeltaGrid Research Engine in public Demo Mode with deterministic sanitized fixtures. Restricted workspaces are not publicly available.",
};

export default function Page() {
  return <PublicResearchDemo />;
}
