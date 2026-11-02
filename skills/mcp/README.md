# MCP

Skills for MCP servers: judging what an agent meets when it uses one, from
the tool list and help to the errors it gets back.

- **[mcp-insights](./mcp-insights/SKILL.md)**: Review an MCP server the way PageSpeed Insights reviews a web page: five scores from 0 to 100 (protocol, agent guidance, error recovery, context cost, safety), context vitals such as tool list size, agent trials that show whether a fresh agent finds the help it needs, and ranked suggestions, in one self-contained HTML report. Works from the outside on any stdio or Streamable HTTP server and is read-only unless you give it a sandbox. Needs `python3`; trials need Claude Code.
