# Enable MCP Servers for the Red Team

> **Request from:** Red Team / Penetration Testing  
> **Purpose:** Allow our team to use MCP (Model Context Protocol) servers in VS Code with GitHub Copilot for security tooling integration (e.g., Burp Suite MCP, BrowserMCP).  
> **Urgency:** Currently blocking our workflow — MCP servers are invisible to Copilot.  
> **Contact:** Willem Smit (willem-smit_slm)

---

## Background

### What Are MCP Servers?

MCP servers extend Copilot's capabilities by connecting it to external tools. Our team needs two:

| Server | Type | What It Does | Connects To |
|--------|------|-------------|-------------|
| **Burp Suite MCP** | HTTP | Lets Copilot send/inspect HTTP requests through Burp's intercepting proxy | `localhost:9876` |
| **BrowserMCP** | stdio | Lets Copilot automate a browser for authenticated web testing | Local Chrome process |

Both run entirely on the analyst's machine. No data leaves the local environment beyond what Copilot already processes.

### Current Problem

The `SLM-Co-Pilot` GitHub org pushes this policy to VS Code:

```json
{
  "mcp": true,
  "mcpAccess": "registry_only",
  "mcpRegistryUrl": "https://mcpregistrygithubenterprisesgt.data.westeurope.azure-apicenter.ms/workspaces/default"
}
```

This means VS Code **only** allows MCP servers published to the enterprise registry. Locally-configured servers (in `mcp.json`) are silently blocked. This is a server-side policy — it cannot be overridden by editing local files on the machine.

---

## Options

### Option A: Add Our Servers to the Enterprise MCP Registry (Recommended)

Keep `mcpAccess: registry_only` unchanged. Instead, publish our two MCP server definitions to the existing enterprise registry. This is the least-disruptive path.

**Pros:**
- No policy change needed — keeps `registry_only` for the whole org
- Servers become available to anyone in the org who needs them
- Centrally managed and auditable

**Cons:**
- All `SLM-Co-Pilot` members can see the servers (but they're harmless — Burp MCP connects to `localhost:9876`, so it silently fails for anyone not running Burp)
- Registry changes require admin access to the Azure API Center instance

#### Step-by-Step: Add Servers to Registry

The enterprise MCP registry is hosted at:
```
https://mcpregistrygithubenterprisesgt.data.westeurope.azure-apicenter.ms/workspaces/default
```

This is an **Azure API Center** instance. To add MCP servers:

1. **Open Azure Portal** → Navigate to the API Center resource backing this URL
   - Resource is in the `westeurope` region
   - Look for an API Center resource with a name like `mcpregistrygithubenterprisesgt`

2. **Register the Burp Suite MCP server:**

   Add an API entry with this MCP server definition:
   ```json
   {
     "name": "burpSuite",
     "description": "Burp Suite intercepting proxy — sends and inspects HTTP requests for web security testing",
     "type": "http",
     "url": "http://127.0.0.1:9876/"
   }
   ```

3. **Register the BrowserMCP server:**

   Add an API entry with this MCP server definition:
   ```json
   {
     "name": "browsermcp",
     "description": "Browser automation for authenticated web security testing via Playwright",
     "type": "stdio",
     "command": "npx",
     "args": ["@anthropic-ai/browsermcp@latest"]
   }
   ```

   > **Note:** The exact `command` and `args` may vary depending on how BrowserMCP is packaged in your environment. The above is the standard npm distribution. If a wrapper script is used, replace with the script path.

4. **Verify** — After adding, team members restart VS Code and:
   - Open Extensions view (`Ctrl+Shift+X`) → type `@mcp` → the new servers should appear
   - Or run **Command Palette** → `MCP: List Servers`

#### If Azure API Center Access Is Unclear

The registry URL format (`*.data.westeurope.azure-apicenter.ms`) confirms this is Azure API Center. The admin who set up the GitHub enterprise MCP integration will know the exact resource. Check:
- Azure Portal → search "API Center" → look for the resource in West Europe
- Or check who configured the `mcpRegistryUrl` in the GitHub org's Copilot policy settings

---

### Option B: Create a Separate GitHub Org for Red Team (Most Control)

Create a dedicated org (e.g., `SLM-RedTeam`) with its own Copilot policy.

**Pros:**
- Full independence — set `mcpAccess: all` so the team can use any local MCP server
- No impact on `SLM-Co-Pilot` org or its members
- Can also have independent model access, content exclusion, and other Copilot policies

**Cons:**
- Requires Copilot Business seats assigned from the new org
- More administrative overhead (separate org to manage)
- Team members may need to switch which GitHub account VS Code uses

#### Step-by-Step: Separate Org

1. **Create org** — GitHub.com → Create new organization → `SLM-RedTeam` (or similar)
2. **Add to enterprise** — Enterprise admin adds `SLM-RedTeam` to the enterprise
3. **Assign Copilot seats** — Purchase/assign Copilot Business seats for red team members in the new org
4. **Set MCP policy:**
   - `SLM-RedTeam` → Settings → Copilot → Policies → MCP servers in Copilot → set `mcpAccess: all`
5. **Invite team members** — Add red team GitHub accounts to `SLM-RedTeam`
6. **VS Code** — Team members sign in with their GitHub account. If they belong to multiple orgs, Copilot uses the org that assigned their seat. They may need to select the correct org in VS Code.

---

### Option C: Change Policy to `all` Org-Wide (Simplest but Broadest)

Change `mcpAccess` from `registry_only` to `all` on `SLM-Co-Pilot`.

**Where:** github.com → `SLM-Co-Pilot` → Settings → Copilot → Policies → MCP servers in Copilot

| Current | Change To | Effect |
|---------|-----------|--------|
| `registry_only` | `all` | Everyone in `SLM-Co-Pilot` can use local MCP servers |

**Pros:** Single toggle, instant fix  
**Cons:** Allows all 200+ org members (or however many) to configure arbitrary local MCP servers — may not align with security posture

---

## Recommendation

**Option A** (add to registry) is the safest path that doesn't change any policies. The servers connect to `localhost` so they're inherently harmless to non-red-team members — they just won't have Burp or BrowserMCP running locally.

If the team's tooling needs grow beyond two servers and we need the flexibility to iterate quickly without registry changes each time, **Option B** (separate org) gives us full autonomy.

---

## Security Notes

- Both MCP servers run locally — no additional network exposure
- VS Code prompts users to trust each MCP server before starting it
- MCP server sandboxing is available on Linux/macOS to restrict file system and network access per server
- Burp Suite MCP requires Burp to be running with the MCP extension enabled — without it, the server is unreachable
- BrowserMCP launches a local browser instance — standard browser security applies

---

## Verification (After Any Option)

Team members restart VS Code and run:

1. **Command Palette** → `Developer: Policy Diagnostics`
   - Option A: `chat.mcp.access` stays `"registry"`, servers appear from registry
   - Option B/C: `chat.mcp.access` shows `"all"`

2. **Command Palette** → `MCP: List Servers`
   - Burp Suite and BrowserMCP should appear and start successfully

3. **Test in chat** — Open Copilot Chat and ask it to use a Burp or browser tool

---

## References

- [VS Code: Manage AI settings in enterprise — MCP server access](https://code.visualstudio.com/docs/enterprise/ai-settings#_configure-mcp-server-access)
- [VS Code: Add and manage MCP servers](https://code.visualstudio.com/docs/copilot/chat/mcp-servers)
- [GitHub: Managing policies for Copilot in your organization](https://docs.github.com/en/copilot/how-tos/administer/organizations/managing-policies-for-copilot-in-your-organization)
- [GitHub: Managing policies for Copilot in your enterprise](https://docs.github.com/en/copilot/how-tos/administer/enterprises/managing-policies-and-features-for-copilot-in-your-enterprise)
- [GitHub: Configure MCP server access](https://docs.github.com/en/copilot/how-tos/administer-copilot/configure-mcp-server-access)
- [Azure API Center documentation](https://learn.microsoft.com/en-us/azure/api-center/)
