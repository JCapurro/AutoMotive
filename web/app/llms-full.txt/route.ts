import { markdownResponse } from "@/lib/llms-route";
import { llmsFullTxt } from "@/lib/llms";

// PAR-04: like /guias, static, regenerated at most once an hour and at once on publishing.
export const revalidate = 3600;

/** /llms-full.txt: the full text of every published guide, in Markdown. */
export async function GET(): Promise<Response> {
  return markdownResponse(llmsFullTxt);
}
