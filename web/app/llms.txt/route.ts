import { markdownResponse } from "@/lib/llms-route";
import { llmsTxt } from "@/lib/llms";

// PAR-04: like /guias, static, regenerated at most once an hour and at once on
// publishing (revalidatePath in app/admin/guides/actions.ts).
export const revalidate = 3600;

/** /llms.txt (llmstxt.org): the site in a paragraph and each published guide. */
export async function GET(): Promise<Response> {
  return markdownResponse(llmsTxt);
}
