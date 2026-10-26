# OWASP identifiers for the mapping column

Use the ID with its year, because the numbering moves between editions (LLM06 means
Excessive Agency in 2025 and Unbounded Consumption in 2026). Pick the most specific
list: a classic web bug gets a Web ID, a model-level issue an LLM ID, an autonomy or
tool issue an ASI ID. One threat can map to two lists (an IDOR reached through a
chatbot tool is A01:2025 and LLM03:2026).

## OWASP Top 10:2025 (web applications)

| ID | Name | Typical CWEs |
| --- | --- | --- |
| A01:2025 | Broken Access Control (SSRF now sits here) | CWE-639 IDOR, CWE-862 missing authorization, CWE-284, CWE-918 SSRF, CWE-352 CSRF |
| A02:2025 | Security Misconfiguration | CWE-16, CWE-611, default credentials, verbose errors |
| A03:2025 | Software Supply Chain Failures | CWE-1395, CWE-829 |
| A04:2025 | Cryptographic Failures | CWE-327, CWE-321, CWE-798 hardcoded credentials, CWE-295 |
| A05:2025 | Injection (includes XSS) | CWE-89, CWE-79, CWE-78, CWE-94 |
| A06:2025 | Insecure Design | CWE-840 business logic errors, CWE-602 client-side enforcement |
| A07:2025 | Authentication Failures | CWE-287, CWE-384 session fixation, CWE-307 brute force |
| A08:2025 | Software or Data Integrity Failures | CWE-502 deserialization, CWE-345 |
| A09:2025 | Security Logging & Alerting Failures | CWE-778, CWE-532 secrets in logs |
| A10:2025 | Mishandling of Exceptional Conditions | CWE-755, CWE-209 |

Source: https://owasp.org/Top10/2025/

## OWASP API Security Top 10 (2023)

For HTTP APIs, mobile backends and anything consumed without a browser. API1 and
API5 are the API-side names for the IDOR and role checks that A01:2025 covers.

| ID | Name |
| --- | --- |
| API1:2023 | Broken Object Level Authorization |
| API2:2023 | Broken Authentication |
| API3:2023 | Broken Object Property Level Authorization (mass assignment, excessive data exposure) |
| API4:2023 | Unrestricted Resource Consumption |
| API5:2023 | Broken Function Level Authorization |
| API6:2023 | Unrestricted Access to Sensitive Business Flows |
| API7:2023 | Server Side Request Forgery |
| API8:2023 | Security Misconfiguration |
| API9:2023 | Improper Inventory Management |
| API10:2023 | Unsafe Consumption of APIs |

Source: https://owasp.org/API-Security/editions/2023/en/0x11-t10/

## OWASP Top 10 for LLM Applications 2026 (model as a component)

| ID | Name |
| --- | --- |
| LLM01:2026 | Prompt Injection (direct, indirect, cross-modal) |
| LLM02:2026 | Sensitive Information Disclosure |
| LLM03:2026 | Excessive Agency |
| LLM04:2026 | Supply Chain (models, adapters, datasets) |
| LLM05:2026 | Data and Model Poisoning |
| LLM06:2026 | Unbounded Consumption (denial of wallet, model theft) |
| LLM07:2026 | Misinformation |
| LLM08:2026 | Hidden Context Exposure (formerly System Prompt Leakage) |
| LLM09:2026 | Vector and Embedding Weaknesses |
| LLM10:2026 | Improper Output Handling (includes insecure generated code) |

Source: https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/

## OWASP Top 10 for Agentic Applications 2026 (model as an actor)

| ID | Name |
| --- | --- |
| ASI01 | Agent Goal Hijack |
| ASI02 | Tool Misuse & Exploitation |
| ASI03 | Identity & Privilege Abuse |
| ASI04 | Agentic Supply Chain Vulnerabilities |
| ASI05 | Unexpected Code Execution (RCE) |
| ASI06 | Memory & Context Poisoning |
| ASI07 | Insecure Inter-Agent Communication |
| ASI08 | Cascading Failures |
| ASI09 | Human-Agent Trust Exploitation |
| ASI10 | Rogue Agents |

Source: https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/

## OWASP MCP Top 10 (beta, 2025 numbering)

MCP01 Token Mismanagement & Secret Exposure · MCP02 Privilege Escalation via Scope
Creep · MCP03 Tool Poisoning · MCP04 Software Supply Chain Attacks & Dependency
Tampering · MCP05 Command Injection & Execution · MCP06 Intent Flow Subversion ·
MCP07 Insufficient Authentication & Authorization · MCP08 Lack of Audit and Telemetry
· MCP09 Shadow MCP Servers · MCP10 Context Injection & Over-Sharing

Source: https://owasp.org/www-project-mcp-top-10/ (check for a newer edition before citing)

## OWASP Agentic Skills Top 10 (AST10, draft v1)

AST01 Malicious Skills · AST02 Supply Chain Compromise · AST03 Over-Privileged Skills
· AST04 Insecure Metadata · AST05 Untrusted External Instructions · AST06 Weak
Isolation · AST07 Update Drift · AST08 Poor Scanning · AST09 No Governance ·
AST10 Cross-Platform Reuse

Source: https://owasp.org/www-project-agentic-skills-top-10/

## Related frameworks

- Shostack's four-question frame: https://github.com/adamshostack/4QuestionFrame
- Lethal trifecta: https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- Agents Rule of Two: https://ai.meta.com/blog/practical-ai-agent-security/
- Multi-agent systems (out of scope for this skill): OWASP Multi-Agentic System Threat
  Modelling Guide and CSA MAESTRO, available as the `multi-agentic-threat-model` play
  in the OWASP Secure Agent Playbook: https://owasp.org/secure-agent-playbook/
