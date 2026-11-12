# Cloud Network Feasibility

**Repository:** Sports Fixtures & Change Tracker
**Assessment date:** 2026-11-11
**Architecture assessed:** Render Free web service, Azure SQL Database Free, and
GitHub Actions scheduled synchronization
**Assessment type:** Provider-documentation review only. No cloud account, firewall,
database, workflow, network connection, or deployment was inspected or changed.

## Decision

### Exact $0 architecture: **NO-GO** for a security-sensitive public deployment

The architecture is technically connectable, but it does not provide a sufficiently
stable or narrow network boundary for the scheduled writer:

- Render Free uses shared, region-specific outbound IP ranges. Those ranges can be
  allowlisted, but they are shared with other Render services and can change.
- Standard GitHub-hosted runners use dynamically assigned shared infrastructure. GitHub
  explicitly recommends against using their published runner ranges as internal
  allowlists.
- Per-job Azure SQL firewall rules can work as an operational workaround, but a failed
  or forcibly terminated job can leave a rule behind. Rule changes can take up to five
  minutes to apply, and deletion is not an instantaneous security boundary.
- Azure OIDC removes long-lived Azure credentials from GitHub Actions, but it does not
  provide a stable source IP, a private route to Azure SQL, or database permissions by
  itself.

### Non-production demonstration: **CONDITIONAL GO** only

A low-sensitivity, disposable proof of concept could use Azure SQL's public endpoint,
the current Render regional ranges, and a tightly controlled temporary GitHub firewall
rule. This is not an acceptable production or privacy-sensitive design. It requires
manual monitoring, an explicit auto-pause/no-overage billing choice, and acceptance
that synchronization may fail during IP or firewall changes.

## Recommended networking design

The recommended design separates public serving, database access, and synchronization:

1. Keep Azure SQL public network access disabled and expose it through a Private
   Endpoint in an Azure virtual network. Azure documents that a private endpoint does
   not disable public routing automatically; public access must be explicitly denied
   after the private path is validated. See [Azure SQL Private Link
   guidance](https://learn.microsoft.com/en-us/azure/azure-sql/database/private-endpoint-overview).

2. Run synchronization from a controlled Azure network: preferably an Azure-hosted
   worker with a managed identity, or a GitHub larger/self-hosted runner with approved
   Azure networking. The runner should reach Azure SQL privately and should not need to
   mutate SQL firewall rules for every job.

3. Either move the FastAPI service into the same controlled Azure network, or accept
   that a Render-hosted API requires a public Azure SQL endpoint. If Render remains the
   public API host, use Render dedicated outbound IPs and narrow Azure SQL firewall
   rules; this is not a $0 option. Render states that dedicated outbound IPs require a
   Pro workspace and an additional monthly fee.

4. Use separate identities:

   - a dashboard identity with only the read permissions required by the repository;
   - a synchronization identity with the importer, provenance, checkpoint, and
     validation permissions required by the schema;
   - a narrowly scoped infrastructure identity, if firewall or network changes are
     unavoidable; and
   - a separate migration identity used only during reviewed deployment.

5. Prefer Microsoft Entra authentication for Azure SQL. GitHub Actions can use OIDC
   and `azure/login` without a long-lived Azure secret, but the repository's current
   `pyodbc` connection convention uses SQL username/password fields. A future token
   implementation must create a contained Entra database user with least privilege and
   pass a database access token through ODBC. Microsoft documents that access-token
   connections must not include `UID`, `PWD`, `Authentication`, or
   `Trusted_Connection` keywords. This is an implementation project, not an assumption
   that OIDC already works with the current code.

The network shape is therefore:

```text
Preferred:
  Public browser -> public API in controlled/Azure network
                         | private endpoint / VNet
                         v
                    Azure SQL Database

  Scheduled sync -> controlled Azure/VNet runner -> private endpoint -> Azure SQL

Render-preserving alternative, not $0:
  Public browser -> Render API -- dedicated egress IP --> Azure SQL public endpoint
  Scheduled sync -> controlled runner/private path -------------> Azure SQL
```

## Verified provider facts

### Render outbound networking

Render documents that services use region-specific CIDR ranges and that a service may
use any address within its associated ranges. The ranges are shared by all services in
the same region; they are not a private identity for this application. The authoritative
list is shown in the service's Dashboard **Connect → Outbound** view, so this review did
not invent or record a current range list.

Sources: [Render outbound IP addresses](https://render.com/docs/outbound-ip-addresses),
[Render regions](https://render.com/docs/regions).

Render also documents that default outbound IPs can rotate and that established
connections may be reset during routing changes. The application must reconnect and
retry safely; a successful previous connection does not prove that the next connection
will originate from the same address.

Source: [Render outbound connection resets](https://render.com/docs/outbound-connection-resets).

Dedicated outbound IPs provide a stronger allowlist, but Render documents that they
require a Pro workspace or higher and an additional monthly fee. Each IP set contains
three IPv4 addresses, and a service may use any address in its assigned set.

Source: [Render dedicated IPs](https://render.com/docs/dedicated-ips).

### Azure SQL firewall and private access

Azure SQL Database has a public endpoint that denies connections until network access
is explicitly allowed. Server-level rules apply to all databases on a logical server;
database-level rules are narrower but require separate T-SQL management. Azure SQL
firewall rules use inclusive start and end IPv4 addresses. The server-level rule limit
is 256, and the documented database-level default is also up to 256 rules.

A Render CIDR therefore cannot be treated as a single secret or identity. It must be
reviewed and represented as the appropriate address range, and the resulting exposure
includes other Render services using that shared range. The number of current Render
ranges and the resulting rule count must be checked in the Render service dashboard
before any configuration.

Azure documents that firewall modifications can take up to five minutes to take effect.
This applies directly to the proposed temporary-rule pattern: a job may still be unable
to connect after the create operation reports success, and a deleted rule may remain
effective for a period while the gateway configuration propagates.

Source: [Azure SQL IP firewall rules](https://learn.microsoft.com/en-au/azure/azure-sql/database/firewall-configure?view=azuresql).

The **Allow Azure services and resources to access this server** switch is not a safe
replacement. Microsoft documents that it creates a `0.0.0.0` rule allowing resources
inside the Azure boundary, including resources in other customers' subscriptions. It
does not mean “only this GitHub workflow” or “only this subscription.” It must remain
disabled.

Source: [Azure SQL network access controls](https://learn.microsoft.com/azure/azure-sql/database/network-access-controls-overview).

Private Endpoints provide the stronger design: clients use a private IP in an Azure
virtual network, and public access can then be denied. A standard Render Free service
is not attached to the Azure virtual network, so it cannot use this path directly.

Source: [Azure Private Link for Azure SQL](https://learn.microsoft.com/en-us/azure/azure-sql/database/private-endpoint-overview).

### GitHub-hosted runner networking

Standard GitHub-hosted runners receive dynamically assigned addresses from shared
infrastructure. GitHub publishes many ranges through its metadata API and updates the
list weekly, but explicitly says it does not recommend using those ranges as allowlists
for internal resources. GitHub instead points users toward larger runners with static
IP ranges or self-hosted runners.

Sources: [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[About GitHub IP addresses](https://docs.github.com/en/enterprise-cloud@latest/authentication/keeping-your-account-and-data-secure/about-githubs-ip-addresses).

GitHub larger runners can provide static IP ranges or Azure private networking, but
larger runners are available to organizations and enterprises on GitHub Team or GitHub
Enterprise Cloud plans. Static IP ranges require GitHub Enterprise Cloud, and larger
runners are billed by execution time. Azure private networking is also a larger-runner
feature, not a standard free-runner feature.

Sources: [GitHub larger runners](https://docs.github.com/en/actions/concepts/runners/larger-runners),
[GitHub private networking for larger runners](https://docs.github.com/en/organizations/managing-organization-settings/about-azure-private-networking-for-github-hosted-runners-in-your-organization).

### Azure OIDC authentication

GitHub OIDC is suitable for replacing a long-lived Azure service-principal secret in a
workflow. The workflow needs `id-token: write`; that permission only permits fetching an
OIDC token and does not itself grant Azure resource permissions. Azure must have a
federated identity credential that restricts the trusted repository and expected branch,
workflow, event, or protected environment.

The Azure identity still needs explicit Azure RBAC permissions. A job able to create or
delete SQL firewall rules needs permissions such as
`Microsoft.Sql/servers/firewallRules/read`, `/write`, and `/delete`; these are network
control-plane permissions and are distinct from SQL database data-plane roles. A
compromised workflow with those permissions could change access for every database on
the logical server, so the identity should be scoped to a dedicated server/resource
where possible and should not also be the dashboard identity.

Sources: [GitHub OIDC in Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure),
[Microsoft Azure OIDC guide](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect),
[Azure database RBAC permissions](https://learn.microsoft.com/en-us/azure/role-based-access-control/permissions/databases).

OIDC is not a network tunnel and does not automatically authenticate the current
`pyodbc` connection. Microsoft documents separate ODBC support for Microsoft Entra
access tokens. The token must be acquired for the Azure SQL resource and passed through
the ODBC access-token attribute, with the incompatible username/password keywords
removed from the connection string.

Source: [Microsoft Entra authentication with ODBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/using-azure-active-directory?view=sql-server-ver17).

## Temporary per-job firewall rules: feasibility and failure analysis

The pattern is technically possible:

1. GitHub Actions authenticates to Azure through a narrowly scoped federated OIDC
   identity.
2. The job determines its actual egress IPv4 address and creates one uniquely named
   Azure SQL firewall rule with equal start and end addresses.
3. The job waits for the rule operation and retries the database connection during the
   documented propagation window.
4. The job performs synchronization under a single workflow concurrency group.
5. An unconditional cleanup step deletes only that run's exact rule name.

It is not a sufficient security design for this project for the following reasons:

- **Crash cleanup:** `if: always()` cleanup helps when the workflow reaches its final
  step, but it cannot guarantee deletion after runner loss, forced cancellation,
  provider outage, OIDC failure, or a process crash. Azure firewall rules do not have a
  documented per-rule expiration in this model. A separate reaper would be required to
  delete stale, strictly prefixed rules after a reviewable TTL.
- **Propagation:** Create and delete operations can be delayed by up to five minutes.
  The connection may fail after creation, and access may remain effective after
  deletion. Cleanup must therefore be treated as eventual, not immediate.
- **Concurrency:** GitHub Actions concurrency can serialize runs in one workflow group,
  but it does not prevent another workflow, a manual Azure operator, a different
  repository identity, or a stale prior rule from changing the server. A dedicated SQL
  server and a database-backed operational lease are safer than relying only on the
  workflow keyword.
- **Privilege:** The identity that mutates firewall rules controls the network boundary
  of the logical server. Giving the data-import job that permission violates least
  privilege unless the server is dedicated and the role is tightly scoped.
- **Rule collisions:** A deterministic rule name could overwrite another run's rule;
  a unique name avoids that but increases stale-rule accumulation. Cleanup must verify
  both rule name and exact IP before deleting anything.
- **Egress identity:** The IP observed by a runner can change between the discovery
  request and the SQL connection, and the published GitHub list is not a substitute for
  the actual job egress address. A job can still fail even if the metadata list was
  recently refreshed.
- **Auditability:** Firewall creation, deletion, and cleanup failures need private
  logging without writing tokens, SQL passwords, or full connection strings. The
  current repository has no Azure firewall lifecycle implementation.

This pattern may be acceptable for a disposable lab database with no sensitive data and
manual stale-rule monitoring. It is not approved as the sole control for a public,
persistent application.

## Permissions and identity separation

| Actor | Required network/data capability | Recommended scope | Assessment |
| --- | --- | --- | --- |
| Render API | Read-only SQL queries over TCP 1433 | Dashboard contained user; Render egress only | Feasible only through public SQL endpoint unless Render egress is paid/dedicated |
| GitHub sync | Source retrieval plus SQL import writes | Separate Entra contained user with importer roles | Requires code changes for token auth; standard runner network remains unresolved |
| Firewall manager | Temporary firewall read/write/delete, if retained | Dedicated SQL server/resource and restricted OIDC subject | High-impact control-plane permission; not combined with dashboard identity |
| Migration operator | Schema and grants | Manual, protected identity | Never placed in Render or scheduled workflow |

The current repository's SQL-auth connection convention is not a verified Azure Entra
implementation. A migration must separately create the contained users and grant only
the permissions proven necessary by the repository's SQL operations. Do not grant
`db_owner` or enable broad Azure-service access as a shortcut.

## Reliability and operational consequences

- Render Free services sleep after 15 minutes without inbound traffic and take about a
  minute to wake. Their filesystem is ephemeral, so raw snapshots and logs cannot live
  only on the Render instance. Render may also suspend a free service that generates an
  unusually high volume of outbound traffic, including external database/API traffic.
- Render outbound route changes can reset established database connections. The API
  must use bounded reconnect behavior and must not treat a reset as a data mutation.
- Azure SQL Free tier databases automatically pause after 15 minutes of inactivity and
  have monthly limits. This makes cold-start/resume behavior part of every connection
  test.
- GitHub Actions concurrency is necessary but not sufficient. A single group can stop
  duplicate workflow runs, but it is not a distributed lock shared with Render, manual
  operators, or another workflow.
- No firewall or network behavior was tested from the target Render region, GitHub
  runner, or Azure subscription. These remain deployment gates.

Sources: [Render free services](https://render.com/docs/free),
[GitHub Actions concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency),
[Azure SQL free tier](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-tier).

## Cost and $0 constraints

| Component | Free claim | Cost or availability risk |
| --- | --- | --- |
| Render Free web service | $0 compute within included limits | 15-minute sleep, ephemeral filesystem, shared outbound ranges, outbound bandwidth/build limits, and possible suspension; overages can be billed when a payment method is present |
| Render dedicated outbound IPs | Not part of the Free networking design | Requires Pro workspace and an additional monthly fee |
| Azure SQL Database Free | 100,000 vCore seconds, 32 GB data, and 32 GB backup per database per month; up to 10 databases per subscription | No SLA; auto-pause at the free limit makes the database inaccessible until the next month, while bill-overage keeps it online and charges the subscription |
| GitHub Actions standard hosted runner | Free for standard runners in public repositories; private-repository allowances depend on the account plan | Additional private usage can be billed; the static-IP/larger-runner path is not the standard $0 runner |
| Private Endpoint | Secure network control | Azure documents per-endpoint hourly and data-processing costs; it is not assumed free |
| Temporary firewall rules | No separate application feature fee identified in this review | They still consume database availability/compute during retries and require a privileged Azure identity; stale rules create security cost rather than a reliable free control |

Sources: [Render free plan](https://render.com/docs/free),
[Render billing FAQ](https://render.com/docs/faq),
[Render dedicated IPs](https://render.com/docs/dedicated-ips),
[GitHub Actions billing](https://docs.github.com/en/actions/concepts/billing-and-usage),
[Azure SQL free-tier limits](https://learn.microsoft.com/en-us/azure/azure-sql/database/free-tier-faq),
[Azure Private Link cost optimization](https://learn.microsoft.com/en-us/azure/private-link/private-link-cost-optimization).

The Azure SQL free-tier creation flow defaults to auto-pause at the free limit. The
billing choice must be reviewed manually; do not select bill-overage while claiming a
$0 architecture.

## Unresolved risks and required evidence

The following cannot be concluded from public documentation alone:

1. The exact Render region and current outbound CIDR list for the intended service.
2. Whether the current Render ranges fit within Azure SQL's rule limits after reviewed
   conversion to start/end ranges.
3. Whether the chosen Azure subscription is eligible for the free tier and has no
   conflicting student/offer restriction.
4. Whether the Azure logical server has public access, Entra admin configuration,
   minimum TLS settings, and firewall rules matching the intended design.
5. Whether the current pyodbc/ODBC Driver 18 packaging and token flow work on the
   selected Render build image.
6. The actual GitHub runner egress IP during a job and whether it remains usable for
   the whole connection attempt.
7. The behavior of a forced workflow cancellation, runner loss, Azure ARM outage, and
   stale-rule reaper.
8. Monthly vCore, storage, bandwidth, and GitHub/Render usage under the real polling and
   dashboard traffic pattern.
9. Whether the public API's query workload stays within the Azure free-tier compute
   budget while Render remains available.

No claim of successful connectivity, stable allowlisting, zero cost, data durability,
or production availability should be made until these items are verified separately.

## Implementation gates before reconsidering GO

Do not deploy the exact architecture until all of the following are true:

- The database is a disposable, backed-up target and its Azure free-tier behavior is
  explicitly set to auto-pause rather than bill-overage.
- The Render service's current outbound ranges are recorded from the service dashboard,
  reviewed for breadth, and tested with a read-only dashboard identity.
- The Azure SQL `0.0.0.0` Azure-services rule is disabled, no broad
  `0.0.0.0`-`255.255.255.255` rule exists, and TCP 1433/TLS behavior is verified.
- The GitHub synchronization path uses a controlled/static/private runner, or the
  project is explicitly accepted as a lab-only temporary-firewall experiment with a
  tested stale-rule reaper.
- OIDC trust is limited to this repository and the protected synchronization workflow;
  firewall control and SQL data permissions are separate identities.
- Azure SQL token authentication, least-privilege grants, transaction rollback,
  idempotent replay, and checkpoint behavior are tested against a clean Azure target.
- Raw snapshots and operational logs have a private durable storage design; neither
  Render's ephemeral filesystem nor a GitHub runner workspace is authoritative.
- Cost alerts and automatic stop behavior are configured before any public traffic.

Until these gates are met, the explicit decision for the requested Render Free + Azure
SQL Free + standard GitHub Actions architecture remains **NO-GO**.
