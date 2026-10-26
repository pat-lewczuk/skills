import { openai } from "@ai-sdk/openai";
import { streamText } from "ai";
import { requireUser } from "@/lib/auth";
import { supportTools } from "@/lib/chat/tools";

const SYSTEM = `You are the support assistant for the customer portal.
Help users find and understand their company's requests. When the user wants something
changed, create a request for them. Be concise. Answer in Markdown.`;

export async function POST(req: Request) {
  const user = await requireUser();
  const { messages } = await req.json();
  const result = streamText({
    model: openai("gpt-4o"),
    system: SYSTEM,
    messages,
    tools: supportTools(user),
    maxSteps: 5,
  });
  return result.toDataStreamResponse();
}
