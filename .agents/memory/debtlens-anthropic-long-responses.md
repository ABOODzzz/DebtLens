---
name: Anthropic long statement responses
description: Constraint when extracting large financial statements through the Anthropic Python SDK.
---

Requests that reserve a large output budget for statement extraction must use the Anthropic Python SDK's streaming message interface. The SDK can reject non-streaming calls before sending anything to the model based solely on the requested output limit; this is not evidence that the source document is malformed.

**Why:** a statement upload failed repeatedly with “Streaming is required for operations that may take longer than 10 minutes” because the extraction budget exceeded the SDK's non-streaming threshold.

**How to apply:** consume the final streamed message and check its stop reason before parsing or persisting transactions. Reaching the output limit is an incomplete result, not a valid financial analysis. Streaming the model response does not itself make the admin HTTP upload resilient to proxy timeouts on very large documents.