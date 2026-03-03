# MDI 2.3 Custom Agent Extensions

Two custom agents for [Medical Deep Insights (MDI) 2.3](https://github.com/anthropics/medical-deep-insights), built on the [Strands Agents](https://strandsagents.com/) framework:

| Agent | Icon | Description |
|-------|------|-------------|
| **IT Support Ticket Generator** | 🎫 | Parses IT incident emails (PDF), queries CMDB for app details, assesses severity, generates structured YAML tickets |
| **Medical Device Bidding Agent** | 🏥 | Searches Chinese medical device (MRI/CT/Ultrasound) bidding announcements, matches GE Healthcare products, provides competitive bidding recommendations |

---

## Architecture Overview

Both agents follow MDI's **Single Supervisor + Multiple Sub-Agent Tools** pattern. Each agent acts as the sole supervisor, orchestrating a set of specialized tools (sub-agents) to complete its workflow. Tool calls are coordinated by the LLM through the Strands Agents framework.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MDI Agent Engine (FastAPI)                       │
│                                                                     │
│  ┌──────────────────────┐       ┌────────────────────────────────┐  │
│  │  🎫 IT Ticket Agent   │       │  🏥 Medical Device Bidding    │  │
│  │     (Supervisor)      │       │        Agent (Supervisor)      │  │
│  │                       │       │                                │  │
│  │  ┌─────────────────┐  │       │  ┌──────────────────────────┐  │  │
│  │  │ get_uploaded_file│  │       │  │     search_google        │  │  │
│  │  │   (Reused)       │  │       │  │       (Reused)           │  │  │
│  │  ├─────────────────┤  │       │  ├──────────────────────────┤  │  │
│  │  │  cmdb_lookup ★   │  │       │  │  ge_product_catalog ★    │  │  │
│  │  │     (New)        │  │       │  │        (New)             │  │  │
│  │  ├─────────────────┤  │       │  ├──────────────────────────┤  │  │
│  │  │generate_ticket ★ │  │       │  │   get_uploaded_file      │  │  │
│  │  │  _yaml (New)     │  │       │  │       (Reused)           │  │  │
│  │  ├─────────────────┤  │       │  ├──────────────────────────┤  │  │
│  │  │  current_time    │  │       │  │     current_time         │  │  │
│  │  │   (Reused)       │  │       │  │       (Reused)           │  │  │
│  │  ├─────────────────┤  │       │  ├──────────────────────────┤  │  │
│  │  │     stop         │  │       │  │       stop               │  │  │
│  │  │   (Reused)       │  │       │  │       (Reused)           │  │  │
│  │  └─────────────────┘  │       │  ├──────────────────────────┤  │  │
│  │                       │       │  │     calculator            │  │  │
│  │                       │       │  │       (Reused)            │  │  │
│  └──────────────────────┘       │  └──────────────────────────┘  │  │
│                                  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘

★ = Newly created tool
```

---

## Sub-Agent Tool Summary

### New Tools (Created by this project)

| Tool | File | Used By | Description |
|------|------|---------|-------------|
| `cmdb_lookup` | `agents/tools/cmdb_lookup.py` | IT Ticket Agent | Queries CMDB (CSV) for application metadata by app_id or app_name. Supports exact match and fuzzy search. |
| `generate_ticket_yaml` | `agents/tools/generate_ticket_yaml.py` | IT Ticket Agent | Generates structured YAML support tickets with auto-generated ID (`TKT-YYYYMMDD-XXXXXX`), streams output to user, persists to agent state. |
| `ge_product_catalog` | `agents/tools/ge_product_catalog.py` | Bidding Agent | Searches GE Healthcare product catalog (CSV) by category (MRI/CT/Ultrasound) or product name. Supports bilingual (Chinese/English) queries. |

### Reused Tools (From MDI 2.3 core)

| Tool | Used By | Description |
|------|---------|-------------|
| `get_uploaded_file` | Both | Retrieves user-uploaded file content from agent state by filename. Essential for reading PDF emails and bidding documents. |
| `current_time` | Both | Returns current date/time. Used for ticket timestamps and time-based bidding search. |
| `stop` | Both | Pauses the workflow to wait for user confirmation at key decision points (Human-in-the-Loop). |
| `search_google` | Bidding Agent | Tavily-powered web search with LLM query rewriting. Searches government procurement websites for bidding announcements. |
| `calculator` | Bidding Agent | Performs mathematical calculations for pricing analysis and bid comparisons. |

### Tool Statistics

| Metric | IT Ticket Agent | Bidding Agent | Total Unique |
|--------|:-:|:-:|:-:|
| **New tools** | 2 (`cmdb_lookup`, `generate_ticket_yaml`) | 1 (`ge_product_catalog`) | **3** |
| **Reused tools** | 3 (`get_uploaded_file`, `current_time`, `stop`) | 5 (`search_google`, `get_uploaded_file`, `current_time`, `stop`, `calculator`) | **5** |
| **Total tools** | 5 | 6 | **8** |

### New Data Sources

| File | Records | Used By | Description |
|------|:-------:|---------|-------------|
| `agents/data/cmdb.csv` | 15 | `cmdb_lookup` | Sample CMDB with application metadata (ID, name, support team, email, business unit, criticality) |
| `agents/data/ge_healthcare_products.csv` | 21 | `ge_product_catalog` | GE Healthcare imaging product catalog (MRI, CT, Ultrasound — model, specs, features, competitive advantages) |

---

## Agent 1: IT Support Ticket Generator 🎫

### Overview

Automates IT support ticket creation from incident emails. The agent reads PDF email attachments, cross-references application information against a CMDB, determines severity levels, and generates structured YAML tickets — all with human-in-the-loop confirmation.

### Workflow Diagram

```
                    ┌─────────────────────┐
                    │   User uploads PDF   │
                    │   incident email     │
                    └──────────┬──────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 1: Read Email     │
                  │  [get_uploaded_file]    │
                  │                        │
                  │  Extract:              │
                  │  • Reporter info       │
                  │  • Application name/ID │
                  │  • Issue description   │
                  │  • Severity hints      │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 2: Query CMDB     │
                  │  [cmdb_lookup] ★        │
                  │                        │
                  │  Retrieve:             │
                  │  • App ID & name       │
                  │  • Support team/email  │
                  │  • Business unit       │
                  │  • System criticality  │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 3: Determine      │
                  │  Severity (LLM)        │
                  │                        │
                  │  P1: System outage     │
                  │  P2: Major feature out │
                  │  P3: Minor issue       │
                  │  P4: Cosmetic/enhance  │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 4: Present &      │
                  │  Confirm [stop]        │
                  │                        │
                  │  Show analysis to user │
                  │  Wait for approval     │
                  └────────────┬───────────┘
                               │ User confirms
                               ▼
                  ┌────────────────────────┐
                  │  Step 5: Generate       │
                  │  Ticket                │
                  │  [current_time] +      │
                  │  [generate_ticket_yaml]│
                  │  ★                     │
                  │                        │
                  │  Output: YAML ticket   │
                  │  with unique ID        │
                  └────────────────────────┘
```

### Detailed Tool Call Flow

```
User ──upload PDF──▶ Supervisor (LLM)
                        │
                        ├──▶ get_uploaded_file(filename="email.pdf")
                        │    └──▶ Returns: email text content
                        │
                        │    [LLM extracts: reporter, app name, issue]
                        │
                        ├──▶ cmdb_lookup(query="SAP ERP")          ★ New
                        │    └──▶ Returns: {app_id, support_team, criticality, ...}
                        │
                        │    [LLM determines severity: P1-P4]
                        │    [LLM presents analysis to user]
                        │
                        ├──▶ stop()
                        │    └──▶ Pauses workflow, waits for user confirmation
                        │
                        │    [User confirms or adjusts]
                        │
                        ├──▶ current_time()
                        │    └──▶ Returns: "2026-03-03T10:30:00Z"
                        │
                        └──▶ generate_ticket_yaml(                 ★ New
                                app_id="APP-001",
                                severity="P2",
                                summary="SAP login failure",
                                ...
                             )
                             └──▶ Returns: Formatted YAML ticket
                                  Streams: YAML output to user UI
                                  Stores:  Ticket in agent state
```

### Output Example

```yaml
ticket:
  ticket_id: TKT-20260303-a1b2c3
  created_at: "2026-03-03T10:30:00Z"
  status: open
  application:
    app_id: APP-001
    app_name: SAP ERP
    business_unit: Finance
  issue:
    severity: P2
    category: Availability
    summary: SAP login failure affecting all users
    description: >
      Multiple users reporting inability to login to SAP ERP
      since 09:00 UTC. Error message: "Authentication service unavailable."
  assignment:
    support_team: ERP Support Team
    team_email: erp-support@company.com
  reporter:
    name: John Smith
    email: john.smith@company.com
```

### Customization

Replace `agents/data/cmdb.csv` with your own CMDB data. Required CSV columns:

```
app_id,app_name,description,support_team,team_email,business_unit,criticality,environment,status
```

Or set `CMDB_FILE_PATH` environment variable to point to an external file.

---

## Agent 2: Medical Device Bidding Agent 🏥

### Overview

Helps GE Healthcare sales teams monitor Chinese medical imaging equipment (MRI, CT, Ultrasound) bidding/procurement announcements. The agent searches government procurement websites, matches bid requirements against GE's product catalog, and generates competitive analysis with bidding recommendations.

### Workflow Diagram

```
                    ┌─────────────────────┐
                    │  User specifies:     │
                    │  • Device type       │
                    │  • Region            │
                    │  • Time range        │
                    └──────────┬──────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 1: Get Time       │
                  │  [current_time]        │
                  │                        │
                  │  Establish search      │
                  │  time baseline         │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 2: Analyze        │
                  │  Requirements (LLM)    │
                  │                        │
                  │  Extract: device type, │
                  │  region, time range,   │
                  │  budget, hospital tier │
                  │                        │
                  │  If file uploaded:     │
                  │  [get_uploaded_file]   │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 3: Search         │
                  │  Bidding Info          │
                  │  [search_google] ×2-4  │
                  │                        │
                  │  Target domains:       │
                  │  • ccgp.gov.cn         │
                  │  • ggzy.gov.cn         │
                  │                        │
                  │  Parallel queries:     │
                  │  "{region} MRI 招标"    │
                  │  "{region} CT 采购公告"  │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 4: Present        │
                  │  Results & Confirm     │
                  │  [stop]                │
                  │                        │
                  │  Show bidding items    │
                  │  with source links     │
                  └────────────┬───────────┘
                               │ User confirms
                               ▼
                  ┌────────────────────────┐
                  │  Step 5: Match GE       │
                  │  Products               │
                  │  [ge_product_catalog] ★ │
                  │                        │
                  │  Find matching GE      │
                  │  models by category    │
                  │  and specifications    │
                  └────────────┬───────────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │  Step 6: Competitive    │
                  │  Analysis (LLM)        │
                  │  [calculator]          │
                  │                        │
                  │  Generate report:      │
                  │  • Product matching    │
                  │  • Technical comparison│
                  │  • Pricing strategy    │
                  │  • Competitor analysis │
                  │    (Siemens, Philips,  │
                  │     United Imaging)    │
                  └────────────────────────┘
```

### Detailed Tool Call Flow

```
User ──"搜索浙江省2025年Q4的MRI招标信息"──▶ Supervisor (LLM)
                                                │
                                                ├──▶ current_time()
                                                │    └──▶ Returns: "2026-03-03"
                                                │
                                                │    [LLM parses: region=浙江, device=MRI, time=2025 Q4]
                                                │
                                                ├──▶ search_google(                        (Reused)
                                                │      query="浙江省 MRI 磁共振 招标公告 2025",
                                                │      include_domains="ccgp.gov.cn,ggzy.gov.cn",
                                                │      days=120
                                                │    )
                                                ├──▶ search_google(                        (Reused)
                                                │      query="浙江 磁共振 采购项目 中标公告"
                                                │    )
                                                │    └──▶ Returns: bidding announcements with links
                                                │
                                                │    [LLM formats and presents results]
                                                │
                                                ├──▶ stop()
                                                │    └──▶ Waits for user to confirm
                                                │
                                                │    [User: "继续分析，推荐GE产品"]
                                                │
                                                ├──▶ ge_product_catalog(query="MRI")       ★ New
                                                │    └──▶ Returns: GE MRI product lineup
                                                │         (SIGNA Premier, SIGNA Artist, ...)
                                                │
                                                ├──▶ calculator(expression="850000*0.85")   (Reused)
                                                │    └──▶ Returns: 722500 (pricing calc)
                                                │
                                                └──▶ LLM generates competitive analysis report
                                                     • Recommended GE models
                                                     • Technical spec matching
                                                     • Pricing strategy
                                                     • Competitor comparison (Siemens, Philips, United Imaging)
```

### GE Product Catalog Coverage

| Category | Products | Example Models |
|----------|:--------:|----------------|
| MRI | 7 | SIGNA Premier (3.0T), SIGNA Artist (1.5T), SIGNA Explorer (1.5T), SIGNA Voyager (1.5T) |
| CT | 7 | Revolution Apex (256-row), Revolution CT (256-row), Revolution Maxima (128-row) |
| Ultrasound | 7 | LOGIQ Fortis, Voluson Expert 22, VENUE Series |

### Customization

Replace `agents/data/ge_healthcare_products.csv` with your own product catalog. Required CSV columns:

```
product_id,product_name,category,model_series,description,key_features,target_department,certifications,competitive_advantages
```

Or set `GE_PRODUCT_CATALOG_PATH` environment variable.

---

## What's Included

```
mdi-custom-agents/
├── agents/
│   ├── tools/
│   │   ├── cmdb_lookup.py              # ★ New: CMDB application lookup
│   │   ├── generate_ticket_yaml.py     # ★ New: Ticket YAML generator
│   │   └── ge_product_catalog.py       # ★ New: GE Healthcare product catalog search
│   ├── data/
│   │   ├── cmdb.csv                    # Sample CMDB (15 applications)
│   │   └── ge_healthcare_products.csv  # GE imaging products (21 products)
│   └── agent_config/
│       ├── it_ticket_agent.yaml        # IT ticket agent config snippet
│       └── medical_device_bidding_agent.yaml  # Bidding agent config snippet
├── install.sh                          # Automated installer
└── README.md
```

---

## Quick Install

### Prerequisites

- MDI 2.3 backend (`medical-deep-insights-release-v2.3.0`) already set up
- Python 3.11+ with `pyyaml` available
- `TAVILY_API_KEY` configured in `.env` (required for `search_google`)

### Steps

```bash
# 1. Clone this repo
git clone https://github.com/xiaobing9520-creator/mdi-custom-agents.git

# 2. cd into your MDI 2.3 backend root
cd /path/to/medical-deep-insights-release-v2.3.0

# 3. Run the installer
bash /path/to/mdi-custom-agents/install.sh

# 4. Rebuild & deploy Docker image
export DOCKER_DEFAULT_PLATFORM="linux/amd64"
docker build -f docker/service.dockerfile -t <ECR_REPO>:<TAG> .
docker push <ECR_REPO>:<TAG>

# 5. Update the DeepInsightAlb ECS service (MDI Agent Engine only)
#    Find your cluster & service names (they contain long CDK-generated suffixes):
aws ecs list-clusters | grep -i deepinsightalb
aws ecs list-services --cluster <CLUSTER_FROM_ABOVE>
#    Then update:
aws ecs update-service --cluster <CLUSTER> --service <SERVICE> --force-new-deployment
```

> **Note on ECR Tag Immutability**: If your ECR repository has tag immutability enabled, you cannot overwrite an existing tag (e.g., `latest`). Use a unique tag for each build instead:
> ```bash
> TAG="mdi-custom-$(date +%Y%m%d%H%M%S)"
> docker build -f docker/service.dockerfile -t <ECR_REPO>:$TAG .
> docker push <ECR_REPO>:$TAG
> ```
> Then register a new task definition revision pointing to the new tag before updating the service.

> **Which ECS service?** A full MDI deployment has multiple ECS clusters. Only the
> **DeepInsightAlb** cluster needs updating — it runs the MDI Agent Engine
> (FastAPI + Strands) where `agent.yaml` and tools are deployed.
>
> | Name prefix | Component | Update needed? |
> |-------------|-----------|----------------|
> | `DeepInsightAlb-*` | MDI Agent Engine (FastAPI + Strands agents) | **Yes** |
> | `MDIA-ServiceStack*` | Insights Portal BFF (NestJS) | No |
> | `MDIA-TranslationStack*` | Translation engine | No |
> | `MDIA-InkAiInternalCore*` | Core writing engine | No |

### Import in Insights Portal

1. Navigate to `/agent-engines` in the portal
2. Click **Import**
3. Fill in:
   - **Name**: Any descriptive name
   - **Engine Address**: `http://<ALB_DNS>` (no trailing space!)
   - **API Key**: Your MDI API key (from Secrets Manager)
4. Click **Import** — the portal will auto-discover both agents

> **How to find ALB_DNS and API Key?**
>
> Both values are in the CloudFormation outputs of the `DeepInsightAlb` stack:
>
> ```bash
> # Get the ALB DNS (engine address)
> aws cloudformation describe-stacks --stack-name DeepInsightAlb \
>   --query "Stacks[0].Outputs[?OutputKey=='mdiDocumentUrl'].OutputValue" --output text
> # Returns: http://DeepIn-DeepI-xxxxx.region.elb.amazonaws.com/docs
> # Remove /docs — the Engine Address is the part before it.
>
> # Get the API Key
> SECRET_NAME=$(aws cloudformation describe-stacks --stack-name DeepInsightAlb \
>   --query "Stacks[0].Outputs[?OutputKey=='mdiServiceApiKeyName'].OutputValue" --output text)
> aws secretsmanager get-secret-value --secret-id $SECRET_NAME \
>   --query SecretString --output text
> ```

---

## Manual Install

If you prefer to install manually instead of using the script:

### 1. Copy files

```bash
# From your MDI 2.3 root directory:
cp <repo>/agents/tools/*.py         agents/tools/
cp <repo>/agents/data/*.csv         agents/data/
```

### 2. Register tools in `agents/tools/__init__.py`

Add these lines:

```python
from agents.tools.cmdb_lookup import cmdb_lookup
from agents.tools.generate_ticket_yaml import generate_ticket_yaml
from agents.tools.ge_product_catalog import ge_product_catalog
```

### 3. Register tools in `agents/utils/tool_mapping.py`

Add to the import block:

```python
from agents.tools import (
    # ... existing imports ...
    cmdb_lookup,
    generate_ticket_yaml,
    ge_product_catalog,
)
```

Add to `TOOL_MAP`:

```python
TOOL_MAP = {
    # ... existing entries ...
    "cmdb_lookup": {
        "tool": cmdb_lookup,
        "display_name": "CMDB Lookup",
        "description": "Query CMDB for application details including support team, business unit, and criticality by application ID or name."
    },
    "generate_ticket_yaml": {
        "tool": generate_ticket_yaml,
        "display_name": "Generate Ticket YAML",
        "description": "Generate a structured support ticket YAML file from extracted issue details, CMDB data, and severity assessment."
    },
    "ge_product_catalog": {
        "tool": ge_product_catalog,
        "display_name": "GE Product Catalog",
        "description": "Query GE Healthcare product catalog for imaging equipment details including MRI, CT, and ultrasound systems."
    },
}
```

### 4. Append agent configs to `agents/agent_config/agent.yaml`

Copy the contents of `agents/agent_config/it_ticket_agent.yaml` and `agents/agent_config/medical_device_bidding_agent.yaml` into the `agent_configs:` section of your `agent.yaml`.

### 5. Rebuild and deploy

See steps 4-5 in Quick Install above.

---

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `TAVILY_API_KEY` | Yes | — | Powers `search_google` in the bidding agent |
| `CMDB_FILE_PATH` | No | `agents/data/cmdb.csv` | Override CMDB data location |
| `GE_PRODUCT_CATALOG_PATH` | No | `agents/data/ge_healthcare_products.csv` | Override product catalog location |

## Compatibility

Tested with MDI 2.3.0 (`medical-deep-insights-release-v2.3.0`). Requires the Strands Agents framework with the standard tool discovery mechanism.
