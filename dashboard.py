
import csv
import json
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVE = BASE / "channel_archive.csv"
BACKUP = BASE / "channel_archive.pre_dashboard_backup.csv"

EDITABLE = {
    "channel_status": [
        "Unknown", "Active", "Private", "Restricted", "Deleted"
    ],
    "membership_status": [
        "Unknown", "Joined", "Not joined",
        "Join required", "Request pending"
    ],
    "access_model": [
        "Unknown", "Free", "Ad-gated", "Paid", "Mixed"
    ],
    "content_availability": [
        "Unknown", "Preview available", "Full content available",
        "Payment required", "Ad unlock required",
        "Historical messages available", "Saved locally",
        "Unavailable"
    ],
}

TEXT_FIELDS = ["invite_link", "payment_notes", "verification_notes"]


def load_records():
    with ARCHIVE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f))


def save_records(records):
    if not BACKUP.exists():
        shutil.copy2(ARCHIVE, BACKUP)

    fields = list(records[0].keys())

    temp = BASE / "channel_archive.tmp"

    with temp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    temp.replace(ARCHIVE)


HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TG Manager</title>
<style>
*{box-sizing:border-box}
body{
  margin:0;background:#101318;color:#e8edf4;
  font-family:Segoe UI,Arial,sans-serif
}
header{padding:25px 5%;background:#191f29;border-bottom:1px solid #303846}
h1{margin:0 0 5px;font-size:27px}
.sub{color:#9ba9ba;font-size:13px}
main{max-width:1500px;margin:auto;padding:25px 4%}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.stat,.panel{background:#191f29;border:1px solid #303846;border-radius:12px;padding:17px}
.stat strong{display:block;font-size:27px;margin-bottom:4px}
.stat span{color:#9ba9ba;font-size:13px}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
input,select,textarea,button{
  font:inherit;color:#e8edf4;background:#222b38;
  border:1px solid #3b485a;border-radius:7px;padding:9px
}
input{flex:1;min-width:230px}
button{cursor:pointer;background:#315caa;border:0}
button:hover{background:#3e70c7}
.panel{overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:1100px}
th,td{text-align:left;padding:11px 9px;border-bottom:1px solid #303846;vertical-align:top}
th{color:#9ba9ba;font-size:12px;text-transform:uppercase}
td{font-size:13px}
td select{width:155px;font-size:12px}
td input{width:180px;min-width:150px;font-size:12px}
.name{font-weight:600;max-width:230px;overflow-wrap:anywhere}
.meta{color:#9ba9ba;font-size:11px;margin-top:5px}
.save{padding:7px 12px;font-size:12px}
#message{color:#91d6a5;font-size:13px;margin:10px 0}
#count{color:#9ba9ba;font-size:13px}
@media(max-width:650px){.stats{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>TG Manager</h1>
  <div class="sub">Personal channel archive · Local dashboard · Read-only Telegram connection</div>
</header>
<main>
  <section class="stats">
    <div class="stat"><strong id="total">—</strong><span>Total records</span></div>
    <div class="stat"><strong id="public">—</strong><span>Public usernames</span></div>
    <div class="stat"><strong id="unknown">—</strong><span>Access models unverified</span></div>
  </section>

  <div class="controls">
    <input id="search" placeholder="Search title, username or channel ID...">
    <select id="accessFilter">
      <option value="">All access models</option>
      <option>Unknown</option><option>Free</option>
      <option>Ad-gated</option><option>Paid</option><option>Mixed</option>
    </select>
    <select id="membershipFilter">
      <option value="">All membership statuses</option>
      <option>Unknown</option><option>Joined</option>
      <option>Not joined</option><option>Join required</option>
      <option>Request pending</option>
    </select>
  </div>

  <div id="message"></div>
  <div id="count"></div>

  <section class="panel">
    <table>
      <thead>
        <tr>
          <th>Channel</th>
          <th>Channel status</th>
          <th>Membership</th>
          <th>Access model</th>
          <th>Content availability</th>
          <th>Notes</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </section>
</main>

<script>
let records = [];

const options = {
  channel_status: ["Unknown","Active","Private","Restricted","Deleted"],
  membership_status: ["Unknown","Joined","Not joined","Join required","Request pending"],
  access_model: ["Unknown","Free","Ad-gated","Paid","Mixed"],
  content_availability: [
    "Unknown","Preview available","Full content available",
    "Payment required","Ad unlock required",
    "Historical messages available","Saved locally","Unavailable"
  ]
};

function makeSelect(field, value) {
  const el = document.createElement("select");
  el.dataset.field = field;

  options[field].forEach(option => {
    const item = document.createElement("option");
    item.value = option;
    item.textContent = option;
    item.selected = option === (value || "Unknown");
    el.appendChild(item);
  });
  return el;
}

function makeInput(field, value) {
  const el = document.createElement("input");
  el.dataset.field = field;
  el.value = value || "";
  el.placeholder = field === "verification_notes" ? "Verification notes" :
                   field === "payment_notes" ? "Payment notes" : "Invite link";
  return el;
}

function cell(row, child) {
  const td = document.createElement("td");
  td.appendChild(child);
  row.appendChild(td);
  return td;
}

function render() {
  const query = document.getElementById("search").value.toLowerCase();
  const access = document.getElementById("accessFilter").value;
  const membership = document.getElementById("membershipFilter").value;

  const filtered = records.filter(r => {
    const haystack = [r.title,r.username,r.id].join(" ").toLowerCase();
    return haystack.includes(query) &&
      (!access || r.access_model === access) &&
      (!membership || r.membership_status === membership);
  });

  document.getElementById("count").textContent =
    `Showing ${filtered.length} of ${records.length} records`;

  const tbody = document.getElementById("rows");
  tbody.replaceChildren();

  filtered.forEach(record => {
    const tr = document.createElement("tr");

    const identity = document.createElement("div");
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = record.title || "Untitled";
    identity.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      (record.username || "No public username") + " · ID " + record.id;
    identity.appendChild(meta);
    cell(tr, identity);

    ["channel_status","membership_status","access_model",
     "content_availability"].forEach(field => {
       cell(tr, makeSelect(field, record[field]));
    });

    const notes = document.createElement("div");
    notes.appendChild(makeInput("verification_notes",record.verification_notes));
    notes.appendChild(makeInput("payment_notes",record.payment_notes));
    notes.appendChild(makeInput("invite_link",record.invite_link));
    cell(tr,notes);

    const action = document.createElement("button");
    action.className = "save";
    action.textContent = "Save";
    action.addEventListener("click", () => saveRecord(tr, record.id));
    cell(tr,action);

    tbody.appendChild(tr);
  });
}

async function saveRecord(row, id) {
  const updates = {};
  row.querySelectorAll("[data-field]").forEach(el => {
    updates[el.dataset.field] = el.value;
  });

  const button = row.querySelector("button");
  button.disabled = true;
  button.textContent = "Saving...";

  try {
    const response = await fetch("/api/update", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({id,updates})
    });

    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Save failed");

    const record = records.find(r => r.id === id);
    Object.assign(record,updates);

    document.getElementById("message").textContent =
      "Saved locally. Backup preserved.";
    button.textContent = "Saved";
  } catch(error) {
    document.getElementById("message").textContent =
      "Could not save: " + error.message;
    button.textContent = "Retry";
  } finally {
    button.disabled = false;
  }
}

async function init() {
  const response = await fetch("/api/channels");
  if (!response.ok) throw new Error("Could not load archive");

  records = await response.json();

  document.getElementById("total").textContent = records.length;
  document.getElementById("public").textContent =
    records.filter(r => r.username).length;
  document.getElementById("unknown").textContent =
    records.filter(r => !r.access_model || r.access_model === "Unknown").length;

  render();
}

["search","accessFilter","membershipFilter"].forEach(id => {
  document.getElementById(id).addEventListener("input",render);
});

init().catch(error => {
  document.getElementById("message").textContent = error.message;
});
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/channels":
            try:
                self.send_json(load_records())
            except Exception as error:
                self.send_json({"error": str(error)}, 500)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/update":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20000:
                self.send_json({"error": "Request too large"}, 413)
                return

            payload = json.loads(self.rfile.read(length))
            channel_id = str(payload.get("id", ""))
            updates = payload.get("updates", {})

            records = load_records()
            record = next(
                (r for r in records if r.get("id") == channel_id),
                None
            )

            if record is None:
                self.send_json({"error": "Channel ID not found"}, 404)
                return

            for field, value in updates.items():
                if field in EDITABLE:
                    if value not in EDITABLE[field]:
                        self.send_json({"error": "Invalid classification"}, 400)
                        return
                    record[field] = value

                elif field in TEXT_FIELDS:
                    if not isinstance(value, str) or len(value) > 2000:
                        self.send_json({"error": "Invalid text field"}, 400)
                        return
                    record[field] = value

            record["last_checked"] = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )

            save_records(records)
            self.send_json({"success": True})

        except Exception as error:
            self.send_json({"error": str(error)}, 500)

    def log_message(self, format, *args):
        print(format % args)


if __name__ == "__main__":
    if not ARCHIVE.exists():
        raise SystemExit("channel_archive.csv not found.")

    print("TG Manager dashboard starting...")
    print("Local address: http://127.0.0.1:8765")
    print("Press Ctrl+C to stop.")

    server = HTTPServer(("127.0.0.1", 8765), Handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.server_close()
