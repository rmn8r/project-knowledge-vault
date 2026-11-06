#!/usr/bin/env python3
"""
xer_tool.py - Primavera P6 .xer schedule analysis. Python standard library only.

Part of the `project-knowledge-vault` skill. It covers what the p6xer MCP server
does (summary, activities, WBS, relationships, calendars, resources, assignments,
earned value, activity detail) and adds what that server lacks:

  * longest-path   The real driving path, traced backwards from the project finish
                   (or any activity) through driving relationships using P6's own
                   scheduled dates and calendar-aware lag/gap arithmetic. Not
                   "total float <= 0". It is cross-checked against P6's own
                   longest-path flags when the XER carries them.
  * diff           A baseline/update comparison of two XERs: finish and milestone
                   movement, added/deleted activities, duration, logic, constraint
                   and calendar changes, progress achieved vs planned, actual dates
                   rewritten after the fact, and longest-path churn.
  * dcma           The full DCMA 14-point assessment, with a baseline XER when one
                   is supplied (missed tasks, BEI).
  * float-paths    P6's multiple float paths, when they were calculated.
  * gaps           Milestone gap check across schedule versions (TIA, rebaseline,
                   mitigation): per phase/ROMP, each milestone's movement plus the
                   stagger between phases and the steps inside a phase (e.g. NEA ->
                   H2C -> PFHO), flagging gaps that were squeezed or went out of
                   sequence. Versions can be .xer files or Group,Milestone,Date CSVs
                   (for dates that exist only in a narrative or a mark-up).

Nothing is installed and nothing leaves the machine. Read-only: XER files are never
modified.

Usage (the project defaults to the one flagged for export, else the largest):
  python xer_tool.py projects       <file.xer>
  python xer_tool.py summary        <file.xer> [--proj CODE]
  python xer_tool.py activities     <file.xer> [--status not_started|active|complete|incomplete]
                                    [--type task|milestone|loe|wbs] [--wbs TEXT] [--search TEXT]
                                    [--float-lt DAYS] [--longest-path] [--limit N]
  python xer_tool.py activity       <file.xer> <task_code>
  python xer_tool.py wbs            <file.xer> [--depth N]
  python xer_tool.py relationships  <file.xer> [--code TASK_CODE] [--limit N]
  python xer_tool.py calendars      <file.xer> [--holidays YEAR]
  python xer_tool.py resources      <file.xer>
  python xer_tool.py assignments    <file.xer> [--rsrc TEXT] [--limit N]
  python xer_tool.py longest-path   <file.xer> [--to TASK_CODE] [--near DAYS]
  python xer_tool.py float-paths    <file.xer>
  python xer_tool.py dcma           <file.xer> [--baseline BL.xer] [--details N]
  python xer_tool.py earned-value   <file.xer> [--baseline BL.xer]
  python xer_tool.py diff           <old.xer> <new.xer> [--top N] [--to TASK_CODE]
  python xer_tool.py gaps           <v1.xer|v1.csv> <v2.xer|v2.csv> ... [--labels A,B,..]
                                    [--ref LABEL] [--focus LABEL] [--keys NEA,H2C,PFHO]
                                    [--workdays] [--min-gap N] [--shrink N] [--search TEXT]
                                    [--group REGEX] [--key REGEX]
  python xer_tool.py export         <file.xer> <out_dir> [--tables TASK,TASKPRED,...]

Output options (any command):
  --json        machine-readable output
  --out FILE    also write the Markdown report to FILE
  --csv DIR     also write every table in the report to DIR as CSV

Date conventions: "wd" = working days on the activity's (or project's) calendar,
"cd" = calendar days. Dates are P6's scheduled dates as of the XER's data date;
nothing is rescheduled.
"""
import os, sys, re, csv, json, argparse, datetime as _dt
from collections import defaultdict, Counter, deque

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DT = _dt.datetime
TD = _dt.timedelta
TOL_H = 0.1          # hours; relationship gaps within this are "driving"
EXCEL_EPOCH = _dt.date(1899, 12, 30)

STATUS = {"TK_NotStart": "Not Started", "TK_Active": "In Progress", "TK_Complete": "Complete"}
TTYPE = {"TT_Task": "Task", "TT_Rsrc": "Resource Dependent", "TT_Mile": "Start Milestone",
         "TT_FinMile": "Finish Milestone", "TT_LOE": "Level of Effort", "TT_WBS": "WBS Summary"}
RELTYPE = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}
CSTR = {"CS_MSO": "Start On", "CS_MSOA": "Start On or After", "CS_MSOB": "Start On or Before",
        "CS_MEO": "Finish On", "CS_MEOA": "Finish On or After", "CS_MEOB": "Finish On or Before",
        "CS_ALAP": "As Late As Possible", "CS_MANDSTART": "Mandatory Start",
        "CS_MANDFIN": "Mandatory Finish"}
# DCMA "hard" constraints: they stop the dates from moving with logic.
HARD_CSTR = {"CS_MSO", "CS_MEO", "CS_MSOB", "CS_MEOB", "CS_MANDSTART", "CS_MANDFIN"}
MILESTONES = {"TT_Mile", "TT_FinMile"}
SUMMARY = {"TT_LOE", "TT_WBS"}


# ======================================================================= parsing
class XerError(Exception):
    pass


def read_xer(path):
    """Return ({table: [row dicts]}, header list). Tolerates cp1252/utf-8."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        hint = ""
        if getattr(e, "errno", None) == 22 or "Invalid argument" in str(e):
            hint = (" (on OneDrive/SharePoint this is usually a cloud-only placeholder: "
                    "right-click > Always keep on this device, then retry)")
        raise XerError(f"cannot read {path}: {e}{hint}")
    text = None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    tables, header, cur, fields = {}, [], None, None
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if not line:
            continue
        tag, _, rest = line.partition("\t")
        if tag == "%R" and cur is not None and fields:
            vals = rest.split("\t")
            if len(vals) < len(fields):
                vals += [""] * (len(fields) - len(vals))
            tables[cur].append(dict(zip(fields, vals)))
        elif tag == "%T":
            cur = rest.strip()
            tables.setdefault(cur, [])
            fields = None
        elif tag == "%F":
            fields = rest.split("\t")
        elif tag == "ERMHDR":
            header = rest.split("\t")
    if "TASK" not in tables or "PROJECT" not in tables:
        raise XerError(f"{path} does not look like a P6 XER (no PROJECT/TASK tables)")
    return tables, header


def pdate(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return DT.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def fnum(s, default=0.0):
    try:
        return float(s) if s not in (None, "") else default
    except ValueError:
        return default


def fmt_d(d):
    return d.strftime("%Y-%m-%d") if d else ""


def fmt_dt(d):
    return d.strftime("%Y-%m-%d %H:%M") if d else ""


def r1(x):
    return None if x is None else round(x, 1)


# ===================================================================== calendars
def _parse_tree(s):
    """Parse P6 clndr_data '(0||Name(attrs)(children))' into nested tuples."""
    s = re.sub(r"\s+", "", s.replace("\x7f", ""))
    pos = 0

    def node():
        nonlocal pos
        if s[pos] != "(":
            raise ValueError("expected (")
        pos += 1
        j = s.index("(", pos)
        head = s[pos:j]
        pos = j + 1
        k = s.index(")", pos)
        attrs = s[pos:k]
        pos = k + 1
        if s[pos] != "(":
            raise ValueError("expected children")
        pos += 1
        kids = []
        while s[pos] == "(":
            kids.append(node())
        pos += 1  # end of children
        if s[pos] != ")":
            raise ValueError("expected )")
        pos += 1  # end of node
        name = head.split("||", 1)[1] if "||" in head else head
        return name, attrs, kids

    return node()


def _attrs(a):
    p = a.split("|")
    return {p[i]: p[i + 1] for i in range(0, len(p) - 1, 2)}


def _mins(hhmm, end=False):
    h, m = hhmm.split(":")
    v = int(h) * 60 + int(m)
    return 1440 if (end and v == 0) else v


def _periods(kids):
    out = []
    for _, a, _ in kids:
        d = _attrs(a)
        if "s" in d and "f" in d:
            s, e = _mins(d["s"]), _mins(d["f"], end=True)
            if e > s:
                out.append((s, e))
    return sorted(out)


class Calendar:
    def __init__(self, row):
        self.id = row.get("clndr_id", "")
        self.name = row.get("clndr_name", "") or f"calendar {self.id}"
        self.type = row.get("clndr_type", "")
        self.day_hr = fnum(row.get("day_hr_cnt"), 8.0) or 8.0
        self.week_hr = fnum(row.get("week_hr_cnt"), 40.0)
        self.week = {i: [] for i in range(1, 8)}   # P6: 1=Sunday .. 7=Saturday
        self.exc = {}
        self.parsed = True
        try:
            name, _, kids = _parse_tree(row.get("clndr_data", ""))
            nodes = kids if name == "CalendarData" else [(name, "", kids)]
            for n, _, k in nodes:
                if n == "DaysOfWeek":
                    for dn, _, dk in k:
                        if dn.isdigit() and 1 <= int(dn) <= 7:
                            self.week[int(dn)] = _periods(dk)
                elif n == "Exceptions":
                    for _, a, ek in k:
                        d = _attrs(a)
                        if "d" in d:
                            day = EXCEL_EPOCH + TD(days=int(float(d["d"])))
                            self.exc[day] = _periods(ek)
        except Exception:
            self.parsed = False
        if not any(self.week.values()):
            # unparseable or empty: assume Mon-Fri from 08:00 for day_hr hours
            self.parsed = False
            span = (8 * 60, min(1440, 8 * 60 + int(self.day_hr * 60)))
            for i in range(2, 7):
                self.week[i] = [span]
        self._cache = {}

    def periods(self, d):
        if d in self.exc:
            return self.exc[d]
        return self.week[(d.weekday() + 1) % 7 + 1]

    def day_hours(self, d):
        return sum(e - s for s, e in self.periods(d)) / 60.0

    def work_between(self, a, b, cap=None):
        """Working hours from a to b (negative if b < a). Stops early past cap."""
        if a is None or b is None:
            return None
        if b < a:
            v = self.work_between(b, a, cap)
            return -v
        total = 0.0
        d = a.date()
        end = b.date()
        while d <= end:
            base = DT(d.year, d.month, d.day)
            for s, e in self.periods(d):
                lo = max(base + TD(minutes=s), a)
                hi = min(base + TD(minutes=e), b)
                if hi > lo:
                    total += (hi - lo).total_seconds() / 3600.0
            if cap is not None and total > cap:
                return total
            d += TD(days=1)
        return total

    def add_work(self, a, hours):
        """Move from a by `hours` of working time (backwards when negative)."""
        if a is None or not hours:
            return a
        mins = abs(hours) * 60.0
        d = a.date()
        for _ in range(366 * 30):
            base = DT(d.year, d.month, d.day)
            pers = self.periods(d)
            if hours > 0:
                for s, e in pers:
                    ps, pe = base + TD(minutes=s), base + TD(minutes=e)
                    lo = max(ps, a)
                    if pe <= lo:
                        continue
                    avail = (pe - lo).total_seconds() / 60.0
                    if avail >= mins:
                        return lo + TD(minutes=mins)
                    mins -= avail
                d += TD(days=1)
            else:
                for s, e in reversed(pers):
                    ps, pe = base + TD(minutes=s), base + TD(minutes=e)
                    hi = min(pe, a)
                    if hi <= ps:
                        continue
                    avail = (hi - ps).total_seconds() / 60.0
                    if avail >= mins:
                        return hi - TD(minutes=mins)
                    mins -= avail
                d -= TD(days=1)
        return a

    def workweek(self):
        names = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}
        parts = []
        for i in (2, 3, 4, 5, 6, 7, 1):
            p = self.week[i]
            if p:
                parts.append(names[i] + " " + ",".join(
                    f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}" for s, e in p))
        return "; ".join(parts) or "(no working days)"


ELAPSED = Calendar({"clndr_id": "24h", "clndr_name": "24-hour", "day_hr_cnt": "24",
                    "clndr_data": "(0||CalendarData()(" + "".join(
                        f"(0||{i}()((0||0(s|00:00|f|00:00)())))" for i in range(1, 8)) + "))"})


# ======================================================================= model
class Schedule:
    """One project inside an XER, with lookups for analysis."""

    def __init__(self, path, proj=None):
        self.path = path
        self.tables, self.header = read_xer(path)
        T = self.tables
        projects = T["PROJECT"]
        counts = Counter(t["proj_id"] for t in T["TASK"])
        if proj:
            m = [p for p in projects if proj in (p.get("proj_id"), p.get("proj_short_name"))]
            if not m:
                m = [p for p in projects if proj.lower() in p.get("proj_short_name", "").lower()]
            if not m:
                raise XerError("project %r not in %s; projects: %s" % (
                    proj, os.path.basename(path),
                    ", ".join(p.get("proj_short_name", "") for p in projects)))
            self.project = m[0]
        else:
            flagged = [p for p in projects if p.get("export_flag") == "Y"]
            pool = flagged or projects
            self.project = max(pool, key=lambda p: counts.get(p["proj_id"], 0))
        P = self.project
        self.proj_id = P["proj_id"]
        self.name = P.get("proj_short_name", self.proj_id)
        self.data_date = pdate(P.get("last_recalc_date")) or pdate(P.get("next_data_date"))
        self.opts = next((o for o in T.get("SCHEDOPTIONS", []) if o.get("proj_id") == self.proj_id),
                         (T.get("SCHEDOPTIONS") or [{}])[0])
        self.cals = {c["clndr_id"]: Calendar(c) for c in T.get("CALENDAR", [])}
        default = next((c for c in T.get("CALENDAR", []) if c.get("default_flag") == "Y"), None)
        self.proj_cal = (self.cals.get(P.get("clndr_id"))
                         or (self.cals.get(default["clndr_id"]) if default else None)
                         or (next(iter(self.cals.values())) if self.cals else ELAPSED))
        # all tasks (preds may sit in other projects); "mine" = this project
        self.task = {}
        for t in T["TASK"]:
            t = dict(t)
            for k in ("act_start_date", "act_end_date", "early_start_date", "early_end_date",
                      "late_start_date", "late_end_date", "target_start_date", "target_end_date",
                      "restart_date", "reend_date", "cstr_date", "cstr_date2", "expect_end_date"):
                t["_" + k] = pdate(t.get(k, ""))
            self.task[t["task_id"]] = t
        self.mine = [t for t in self.task.values() if t["proj_id"] == self.proj_id]
        self.by_code = {t["task_code"]: t for t in self.mine}
        self.wbs = {w["wbs_id"]: w for w in T.get("PROJWBS", [])}
        self.preds = defaultdict(list)
        self.succs = defaultdict(list)
        self.rels = []
        for r in T.get("TASKPRED", []):
            if r["task_id"] in self.task and r["pred_task_id"] in self.task:
                self.rels.append(r)
                self.preds[r["task_id"]].append(r)
                self.succs[r["pred_task_id"]].append(r)
        self.rsrc = {r["rsrc_id"]: r for r in T.get("RSRC", [])}
        self.assign = defaultdict(list)
        for a in T.get("TASKRSRC", []):
            self.assign[a["task_id"]].append(a)
        self._gap = {}
        self._lp = {}

    # ---- task helpers
    def cal(self, t):
        return self.cals.get(t.get("clndr_id")) or self.proj_cal

    def days(self, t, hours):
        if hours is None:
            return None
        return hours / (self.cal(t).day_hr or 8.0)

    def tf_days(self, t):
        if t.get("total_float_hr_cnt", "") == "":
            return None
        return self.days(t, fnum(t["total_float_hr_cnt"]))

    def start(self, t):
        return t["_act_start_date"] or t["_early_start_date"] or t["_restart_date"]

    def finish(self, t):
        return t["_act_end_date"] or t["_early_end_date"] or t["_reend_date"]

    def is_complete(self, t):
        return t["status_code"] == "TK_Complete"

    def is_started(self, t):
        return t["status_code"] in ("TK_Active", "TK_Complete")

    def wbs_path(self, wbs_id, names=False):
        parts, seen = [], set()
        w = self.wbs.get(wbs_id)
        while w and w["wbs_id"] not in seen and w.get("proj_node_flag") != "Y":
            seen.add(w["wbs_id"])
            parts.append(w["wbs_name"] if names else w["wbs_short_name"])
            w = self.wbs.get(w.get("parent_wbs_id"))
        return (" > " if names else ".").join(reversed(parts))

    def finish_date(self):
        """Forecast project finish: latest finish of this project's activities."""
        f = [self.finish(t) for t in self.mine if t["task_type"] not in SUMMARY and self.finish(t)]
        return max(f) if f else pdate(self.project.get("scd_end_date"))

    def lag_cal(self, pred, succ):
        mode = self.opts.get("sched_calendar_on_relationship_lag", "rcal_Predecessor")
        if mode == "rcal_Successor":
            return self.cal(succ)
        if mode == "rcal_24Hour":
            return ELAPSED
        if mode == "rcal_ProjDefault":
            return self.proj_cal
        return self.cal(pred)

    def retained_logic(self):
        return self.opts.get("sched_retained_logic", "Y") == "Y" and self.opts.get("sched_progress_override") != "Y"

    def lag_start(self, p):
        """Start date SS/SF lags count from. With P6's 'calculate start-to-start lag
        from Early Start' option, an in-progress predecessor counts from its
        remaining early start (the data date), not its actual start."""
        if p["status_code"] == "TK_Active" and self.opts.get("sched_lag_early_start_flag") == "Y":
            return p["_early_start_date"] or p["_restart_date"] or self.start(p)
        return self.start(p)

    # ---- relationship gap: how much working time the successor waits beyond
    # what this relationship requires. ~0 means the relationship is driving.
    def rel_gap(self, r, cap=None):
        key = (r["task_pred_id"], cap)
        if key in self._gap:
            return self._gap[key]
        p, s = self.task[r["pred_task_id"]], self.task[r["task_id"]]
        typ = r.get("pred_type", "PR_FS")
        gap = None
        if not self.is_complete(s) and s["task_type"] not in SUMMARY:
            active = s["status_code"] == "TK_Active"
            if typ == "PR_FS":
                # retained logic: an FS predecessor still holds the remaining work
                # of a successor that has already started out of sequence
                sdate = s["_early_start_date"] if (not active or self.retained_logic()) else None
            elif typ == "PR_SS":
                # an SS predecessor of a started successor can only hold its finish
                # (matches P6's longest-path flags on in-progress successors)
                if not active:
                    sdate = s["_early_start_date"]
                else:
                    sdate = (s["_early_end_date"] or s["_reend_date"]) if self.retained_logic() else None
            else:
                sdate = s["_early_end_date"] or s["_reend_date"]
            pdate_ = self.finish(p) if typ in ("PR_FS", "PR_FF") else self.lag_start(p)
            if sdate and pdate_:
                lag = fnum(r.get("lag_hr_cnt"))
                ready = self.lag_cal(p, s).add_work(pdate_, lag) if lag else pdate_
                gap = self.cal(s).work_between(ready, sdate, cap)
        self._gap[key] = gap
        return gap

    def driving_preds(self, t):
        out = []
        for r in self.preds[t["task_id"]]:
            p = self.task[r["pred_task_id"]]
            if self.is_complete(p) or p["task_type"] == "TT_WBS":
                continue
            g = self.rel_gap(r, cap=8.0)
            if g is not None and abs(g) <= TOL_H:
                out.append(r)
        return out

    def why_undriven(self, t):
        """Reason an incomplete activity on the path has no driving predecessor."""
        if t["task_type"] == "TT_LOE":
            return "level of effort (its dates follow the activities it spans)"
        if "CS_ALAP" in (t.get("cstr_type"), t.get("cstr_type2")):
            return "As Late As Possible (scheduled back from its successor)"
        if t["status_code"] == "TK_Active":
            return "in progress (started %s; remaining duration drives finish)" % fmt_d(
                t["_act_start_date"])
        es = t["_early_start_date"]
        for ct, cd in ((t.get("cstr_type"), t["_cstr_date"]), (t.get("cstr_type2"), t["_cstr_date2"])):
            if ct and cd and es and ct in ("CS_MSO", "CS_MSOA", "CS_MANDSTART") and \
                    abs(self.cal(t).work_between(cd, es, cap=8.0)) <= TOL_H:
                return "constraint: %s %s" % (CSTR.get(ct, ct), fmt_d(cd))
            if ct and cd and ct in ("CS_MEO", "CS_MEOA", "CS_MANDFIN") and t["_early_end_date"] and \
                    abs(self.cal(t).work_between(cd, t["_early_end_date"], cap=8.0)) <= TOL_H:
                return "constraint: %s %s" % (CSTR.get(ct, ct), fmt_d(cd))
        if self.data_date and es and abs(self.cal(t).work_between(self.data_date, es, cap=8.0)) <= TOL_H:
            return "data date (%s)" % fmt_d(self.data_date)
        if not self.preds[t["task_id"]]:
            return "no predecessor (open start)"
        return "unexplained gap (check external dates, leveling, or out-of-sequence progress)"

    def default_end(self):
        cands = [t for t in self.mine if not self.is_complete(t) and t["task_type"] not in SUMMARY
                 and t["_early_end_date"]]
        if not cands:
            return []
        mx = max(t["_early_end_date"] for t in cands)
        return [t for t in cands if t["_early_end_date"] == mx]

    def longest_path(self, end_code=None):
        """Trace driving relationships back from end activity(ies).
        Returns (ordered task list, drivers {task_id: [rel]}, roots {task_id: reason})."""
        key = end_code or ""
        if key in self._lp:
            return self._lp[key]
        if end_code:
            if end_code not in self.by_code:
                raise XerError(f"activity {end_code!r} not found in {self.name}")
            ends = [self.by_code[end_code]]
        else:
            ends = self.default_end()
        seen, drivers, roots = set(), {}, {}
        q = deque(ends)
        while q:
            t = q.popleft()
            if t["task_id"] in seen:
                continue
            seen.add(t["task_id"])
            # an LOE rides along on the path but does not drive anything upstream
            d = [] if t["task_type"] == "TT_LOE" else self.driving_preds(t)
            drivers[t["task_id"]] = d
            if not d:
                roots[t["task_id"]] = self.why_undriven(t)
            for r in d:
                q.append(self.task[r["pred_task_id"]])
        path = sorted((self.task[i] for i in seen),
                      key=lambda t: (self.start(t) or DT.max, self.finish(t) or DT.max))
        self._lp[key] = (path, drivers, roots, ends)
        return self._lp[key]


# ====================================================================== reports
class Report:
    def __init__(self, title):
        self.title = title
        self.parts = []   # ("kv", heading, [(k, v)]) | ("table", heading, headers, rows) | ("text", heading, str)

    def kv(self, heading, pairs):
        self.parts.append(("kv", heading, pairs))

    def table(self, heading, headers, rows, note=None):
        self.parts.append(("table", heading, headers, rows, note))

    def text(self, heading, body):
        self.parts.append(("text", heading, body))

    def markdown(self):
        out = [f"# {self.title}", ""]
        for p in self.parts:
            if p[1]:
                out += [f"## {p[1]}", ""]
            if p[0] == "kv":
                out += [f"- **{k}:** {v}" for k, v in p[2]] + [""]
            elif p[0] == "text":
                out += [p[2], ""]
            else:
                _, _, headers, rows, note = p
                if note:
                    out += [note, ""]
                if not rows:
                    out += ["_None._", ""]
                    continue
                cell = lambda v: "" if v is None else str(v).replace("|", "\\|").replace("\n", " ")
                out.append("| " + " | ".join(headers) + " |")
                out.append("|" + "|".join("---" for _ in headers) + "|")
                out += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
                out.append("")
        return "\n".join(out)

    def as_json(self):
        doc = {"title": self.title, "sections": []}
        for p in self.parts:
            if p[0] == "kv":
                doc["sections"].append({"heading": p[1], "values": {k: v for k, v in p[2]}})
            elif p[0] == "text":
                doc["sections"].append({"heading": p[1], "text": p[2]})
            else:
                doc["sections"].append({"heading": p[1], "note": p[4],
                                        "rows": [dict(zip(p[2], r)) for r in p[3]]})
        return json.dumps(doc, indent=1, default=str)

    def write_csv(self, folder):
        os.makedirs(folder, exist_ok=True)
        n = 0
        for p in self.parts:
            if p[0] != "table":
                continue
            slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{self.title} {p[1] or ''}").strip("_")[:120]
            with open(os.path.join(folder, slug + ".csv"), "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(p[2])
                w.writerows(p[3])
            n += 1
        return n


def act_row(S, t, extra=()):
    return [t["task_code"], t["task_name"], STATUS.get(t["status_code"], t["status_code"]),
            fmt_d(S.start(t)), fmt_d(S.finish(t)), r1(S.tf_days(t))] + list(extra)


ACT_HDR = ["Code", "Name", "Status", "Start", "Finish", "TF (wd)"]


# ===================================================================== commands
def cmd_projects(args):
    tables, header = read_xer(args.xer)
    counts = Counter(t["proj_id"] for t in tables["TASK"])
    rep = Report(f"Projects in {os.path.basename(args.xer)}")
    if header:
        rep.kv("Export", [("P6 version", header[0] if header else ""),
                          ("Exported", header[1] if len(header) > 1 else ""),
                          ("By", header[4] if len(header) > 4 else "")])
    rep.table("Projects", ["proj_id", "Short name", "Data date", "Finish", "Activities", "Export flag"],
              [[p["proj_id"], p.get("proj_short_name"), p.get("last_recalc_date"),
                p.get("scd_end_date"), counts.get(p["proj_id"], 0), p.get("export_flag", "")]
               for p in tables["PROJECT"]],
              "Use --proj <short name> to pick one; the default is the export-flagged project with the most activities.")
    return rep


def cmd_summary(args):
    S = Schedule(args.xer, args.proj)
    mine = S.mine
    st = Counter(t["status_code"] for t in mine)
    ty = Counter(t["task_type"] for t in mine)
    path, _, _, ends = S.longest_path()
    neg = [t for t in mine if not S.is_complete(t) and (S.tf_days(t) or 0) < 0]
    rep = Report(f"Schedule summary - {S.name}")
    fin = S.finish_date()
    rem_wd = S.proj_cal.work_between(S.data_date, fin) / S.proj_cal.day_hr if (S.data_date and fin) else None
    rep.kv("Project", [
        ("File", os.path.basename(S.path)),
        ("Project", f"{S.name} (id {S.proj_id})"),
        ("Data date", fmt_dt(S.data_date)),
        ("Planned start", S.project.get("plan_start_date", "")),
        ("Forecast finish", fmt_dt(fin)),
        ("Must-finish-by", S.project.get("plan_end_date", "") or "(none)"),
        ("Remaining duration", f"{r1(rem_wd)} wd on {S.proj_cal.name}" if rem_wd is not None else ""),
        ("Default calendar", S.proj_cal.name),
        ("Critical defined as", {"CT_TotFloat": "total float <= %s h" % S.project.get("critical_drtn_hr_cnt", "0"),
                                 "CT_DrivPath": "longest path"}.get(S.project.get("critical_path_type"), S.project.get("critical_path_type", ""))),
        ("Relationship lag calendar", S.opts.get("sched_calendar_on_relationship_lag", "")),
        ("Out-of-sequence progress", "retained logic" if S.opts.get("sched_retained_logic") == "Y"
         else ("progress override" if S.opts.get("sched_progress_override") == "Y" else "actual dates")),
    ])
    rep.table("Counts", ["Measure", "Count"], [
        ["Activities", len(mine)],
        ["Not started / in progress / complete",
         f"{st['TK_NotStart']} / {st['TK_Active']} / {st['TK_Complete']}"],
        ["Tasks / milestones / LOE / WBS summary",
         f"{ty['TT_Task'] + ty['TT_Rsrc']} / {ty['TT_Mile'] + ty['TT_FinMile']} / {ty['TT_LOE']} / {ty['TT_WBS']}"],
        ["Relationships", sum(1 for r in S.rels if r["proj_id"] == S.proj_id)],
        ["WBS elements", sum(1 for w in S.wbs.values() if w["proj_id"] == S.proj_id)],
        ["Calendars", len(S.cals)],
        ["Resources / assignments", f"{len(S.rsrc)} / {sum(len(S.assign[t['task_id']]) for t in mine)}"],
        ["Longest-path activities (incomplete)", len(path)],
        ["Incomplete activities with negative float", len(neg)],
    ])
    ms = sorted([t for t in mine if t["task_type"] in MILESTONES and not S.is_complete(t)],
                key=lambda t: S.finish(t) or DT.max)
    rep.table("Upcoming milestones", ACT_HDR, [act_row(S, t) for t in ms[:40]],
              f"{len(ms)} incomplete milestones" + (" (first 40 shown)" if len(ms) > 40 else ""))
    return rep


def cmd_activities(args):
    S = Schedule(args.xer, args.proj)
    rows = list(S.mine)
    if args.status:
        m = {"not_started": {"TK_NotStart"}, "active": {"TK_Active"}, "complete": {"TK_Complete"},
             "incomplete": {"TK_NotStart", "TK_Active"}}[args.status]
        rows = [t for t in rows if t["status_code"] in m]
    if args.type:
        m = {"task": {"TT_Task", "TT_Rsrc"}, "milestone": MILESTONES, "loe": {"TT_LOE"},
             "wbs": {"TT_WBS"}}[args.type]
        rows = [t for t in rows if t["task_type"] in m]
    if args.wbs:
        k = args.wbs.lower()
        rows = [t for t in rows if k in S.wbs_path(t["wbs_id"]).lower() or k in S.wbs_path(t["wbs_id"], True).lower()]
    if args.search:
        k = args.search.lower()
        rows = [t for t in rows if k in t["task_name"].lower() or k in t["task_code"].lower()]
    if args.float_lt is not None:
        rows = [t for t in rows if S.tf_days(t) is not None and S.tf_days(t) < args.float_lt]
    if args.longest_path:
        lp = {t["task_id"] for t in S.longest_path()[0]}
        rows = [t for t in rows if t["task_id"] in lp]
    rows.sort(key=lambda t: (S.start(t) or DT.max, t["task_code"]))
    rep = Report(f"Activities - {S.name}")
    rep.table(None, ACT_HDR + ["Orig dur (wd)", "Rem dur (wd)", "Type", "WBS"],
              [act_row(S, t, [r1(S.days(t, fnum(t["target_drtn_hr_cnt"]))),
                              r1(S.days(t, fnum(t["remain_drtn_hr_cnt"]))),
                              TTYPE.get(t["task_type"], t["task_type"]), S.wbs_path(t["wbs_id"])])
               for t in rows[:args.limit]],
              f"{len(rows)} matching activities" + (f" (first {args.limit} shown)" if len(rows) > args.limit else ""))
    return rep


def cmd_activity(args):
    S = Schedule(args.xer, args.proj)
    t = S.by_code.get(args.code)
    if not t:
        k = args.code.lower()
        hits = [x for x in S.mine if k in x["task_code"].lower() or k in x["task_name"].lower()]
        if len(hits) == 1:
            t = hits[0]
        else:
            raise XerError(f"activity {args.code!r} not found" + (
                "; candidates: " + ", ".join(h["task_code"] for h in hits[:15]) if hits else ""))
    c = S.cal(t)
    lp = {x["task_id"] for x in S.longest_path()[0]}
    rep = Report(f"{t['task_code']} - {t['task_name']}")
    cs = [f"{CSTR.get(t.get(k), t.get(k))} {fmt_d(t['_' + d])}" for k, d in
          (("cstr_type", "cstr_date"), ("cstr_type2", "cstr_date2")) if t.get(k)]
    rep.kv("Activity", [
        ("Type / status", f"{TTYPE.get(t['task_type'], t['task_type'])} / {STATUS.get(t['status_code'])}"),
        ("WBS", f"{S.wbs_path(t['wbs_id'])} ({S.wbs_path(t['wbs_id'], True)})"),
        ("Calendar", f"{c.name} ({c.day_hr:g} h/day)"),
        ("Original / remaining duration", f"{r1(S.days(t, fnum(t['target_drtn_hr_cnt'])))} / "
                                          f"{r1(S.days(t, fnum(t['remain_drtn_hr_cnt'])))} wd"),
        ("% complete", f"{t.get('phys_complete_pct', '')} ({t.get('complete_pct_type', '')})"),
        ("Actual start / finish", f"{fmt_dt(t['_act_start_date'])} / {fmt_dt(t['_act_end_date'])}"),
        ("Early start / finish", f"{fmt_dt(t['_early_start_date'])} / {fmt_dt(t['_early_end_date'])}"),
        ("Late start / finish", f"{fmt_dt(t['_late_start_date'])} / {fmt_dt(t['_late_end_date'])}"),
        ("Planned start / finish", f"{fmt_dt(t['_target_start_date'])} / {fmt_dt(t['_target_end_date'])}"),
        ("Total / free float", f"{r1(S.tf_days(t))} / {r1(S.days(t, fnum(t.get('free_float_hr_cnt'))))} wd"),
        ("Constraints", "; ".join(cs) or "none"),
        ("On longest path", "yes" if t["task_id"] in lp else "no"),
        ("P6 longest-path flag", t.get("driving_path_flag", "")),
    ])

    def rel_rows(rels, other_key):
        out = []
        for r in rels:
            o = S.task[r[other_key]]
            g = S.rel_gap(r)
            gd = None if g is None else g / (S.cal(t if other_key == "pred_task_id" else o).day_hr or 8)
            drv = "" if g is None else ("DRIVING" if abs(g) <= TOL_H else ("violated" if g < -TOL_H else ""))
            out.append([o["task_code"], o["task_name"], RELTYPE.get(r["pred_type"], r["pred_type"]),
                        r1(S.days(o, fnum(r.get("lag_hr_cnt")))), STATUS.get(o["status_code"]),
                        fmt_d(S.start(o)), fmt_d(S.finish(o)), r1(gd), drv])
        return out

    hdr = ["Code", "Name", "Rel", "Lag (wd)", "Status", "Start", "Finish", "Rel free float (wd)", "Driving"]
    rep.table("Predecessors", hdr, rel_rows(S.preds[t["task_id"]], "pred_task_id"))
    rep.table("Successors", hdr, rel_rows(S.succs[t["task_id"]], "task_id"))
    rep.table("Resource assignments", ["Resource", "Type", "Budget qty", "Actual qty", "Remaining qty",
                                       "Budget cost", "Actual cost", "Remaining cost"],
              [[S.rsrc.get(a["rsrc_id"], {}).get("rsrc_name", a["rsrc_id"]),
                S.rsrc.get(a["rsrc_id"], {}).get("rsrc_type", ""),
                r1(fnum(a.get("target_qty"))), r1(fnum(a.get("act_reg_qty")) + fnum(a.get("act_ot_qty"))),
                r1(fnum(a.get("remain_qty"))), r1(fnum(a.get("target_cost"))),
                r1(fnum(a.get("act_reg_cost")) + fnum(a.get("act_ot_cost"))), r1(fnum(a.get("remain_cost")))]
               for a in S.assign[t["task_id"]]])
    return rep


def cmd_wbs(args):
    S = Schedule(args.xer, args.proj)
    kids = defaultdict(list)
    roots = []
    for w in S.wbs.values():
        if w["proj_id"] != S.proj_id:
            continue
        if w.get("proj_node_flag") == "Y":
            roots.append(w)
        else:
            kids[w.get("parent_wbs_id")].append(w)
    acts = defaultdict(list)
    for t in S.mine:
        acts[t["wbs_id"]].append(t)
    rows = []

    def walk(w, depth):
        sub = [w["wbs_id"]]
        stack = list(kids[w["wbs_id"]])
        while stack:
            x = stack.pop()
            sub.append(x["wbs_id"])
            stack += kids[x["wbs_id"]]
        ts = [t for i in sub for t in acts[i]]
        fins = [S.finish(t) for t in ts if S.finish(t)]
        sts = [S.start(t) for t in ts if S.start(t)]
        done = sum(1 for t in ts if S.is_complete(t))
        tfs = [S.tf_days(t) for t in ts if not S.is_complete(t) and S.tf_days(t) is not None]
        if depth > 0:
            rows.append(["  " * (depth - 1) + w["wbs_short_name"], w["wbs_name"], len(ts),
                         f"{done}/{len(ts)}", fmt_d(min(sts)) if sts else "", fmt_d(max(fins)) if fins else "",
                         r1(min(tfs)) if tfs else ""])
        if args.depth is None or depth < args.depth:
            for k in sorted(kids[w["wbs_id"]], key=lambda x: (fnum(x.get("seq_num")), x["wbs_short_name"])):
                walk(k, depth + 1)

    for r in roots:
        walk(r, 0)
    rep = Report(f"WBS - {S.name}")
    rep.table(None, ["WBS", "Name", "Activities", "Complete", "Start", "Finish", "Min TF (wd)"], rows)
    return rep


def cmd_relationships(args):
    S = Schedule(args.xer, args.proj)
    rels = [r for r in S.rels if r["proj_id"] == S.proj_id or r.get("pred_proj_id") == S.proj_id]
    if args.code:
        t = S.by_code.get(args.code)
        if not t:
            raise XerError(f"activity {args.code!r} not found")
        rels = [r for r in rels if t["task_id"] in (r["task_id"], r["pred_task_id"])]
    rep = Report(f"Relationships - {S.name}")
    c = Counter(RELTYPE.get(r["pred_type"], r["pred_type"]) for r in rels)
    rep.kv("Mix", [(k, f"{v} ({100.0 * v / max(len(rels), 1):.1f}%)") for k, v in c.most_common()] +
           [("Leads (negative lag)", sum(1 for r in rels if fnum(r.get("lag_hr_cnt")) < 0)),
            ("Lags (positive)", sum(1 for r in rels if fnum(r.get("lag_hr_cnt")) > 0))])
    rows = []
    for r in rels[:args.limit]:
        p, s = S.task[r["pred_task_id"]], S.task[r["task_id"]]
        g = S.rel_gap(r)
        rows.append([p["task_code"], p["task_name"], RELTYPE.get(r["pred_type"]), s["task_code"], s["task_name"],
                     r1(S.days(p, fnum(r.get("lag_hr_cnt")))),
                     r1(None if g is None else g / S.cal(s).day_hr),
                     "DRIVING" if (g is not None and abs(g) <= TOL_H) else ""])
    rep.table("Relationships", ["Pred code", "Pred name", "Type", "Succ code", "Succ name", "Lag (wd)",
                                "Rel free float (wd)", "Driving"], rows,
              f"{len(rels)} relationships" + (f" (first {args.limit} shown)" if len(rels) > args.limit else ""))
    return rep


def cmd_calendars(args):
    S = Schedule(args.xer, args.proj)
    use = Counter(t.get("clndr_id") for t in S.mine)
    rep = Report(f"Calendars - {S.name}")
    rep.table(None, ["id", "Name", "Type", "h/day", "h/week", "Work week", "Exceptions", "Activities", "Parsed"],
              [[c.id, c.name, c.type.replace("CA_", ""), c.day_hr, c.week_hr, c.workweek(),
                len(c.exc), use.get(c.id, 0), "yes" if c.parsed else "NO (assumed M-F)"]
               for c in sorted(S.cals.values(), key=lambda c: -use.get(c.id, 0))])
    if args.holidays:
        rows = []
        for c in S.cals.values():
            if not use.get(c.id):
                continue
            for d, p in sorted(c.exc.items()):
                if d.year == args.holidays:
                    rows.append([c.name, fmt_d(d), d.strftime("%a"),
                                 "non-work" if not p else "work %g h" % c.day_hours(d)])
        rep.table(f"Exceptions in {args.holidays} (calendars in use)", ["Calendar", "Date", "Day", "Kind"], rows)
    return rep


def _rate_limits(S):
    lim = {}
    for r in S.tables.get("RSRCRATE", []):
        q = fnum(r.get("max_qty_per_hr"))
        d = pdate(r.get("start_date")) or DT.min
        if q > 0 and (r["rsrc_id"] not in lim or d >= lim[r["rsrc_id"]][0]):
            lim[r["rsrc_id"]] = (d, q)
    return {k: v[1] for k, v in lim.items()}


def cmd_resources(args):
    S = Schedule(args.xer, args.proj)
    mine = {t["task_id"] for t in S.mine}
    agg = defaultdict(lambda: Counter())
    for tid in mine:
        for a in S.assign[tid]:
            g = agg[a["rsrc_id"]]
            g["n"] += 1
            g["bq"] += fnum(a.get("target_qty"))
            g["aq"] += fnum(a.get("act_reg_qty")) + fnum(a.get("act_ot_qty"))
            g["rq"] += fnum(a.get("remain_qty"))
            g["bc"] += fnum(a.get("target_cost"))
            g["ac"] += fnum(a.get("act_reg_cost")) + fnum(a.get("act_ot_cost"))
            g["rc"] += fnum(a.get("remain_cost"))
    limits = _rate_limits(S)
    # over-allocation: spread remaining qty over each assignment's remaining dates
    load = defaultdict(lambda: defaultdict(float))
    for tid in mine:
        t = S.task[tid]
        if S.is_complete(t):
            continue
        for a in S.assign[tid]:
            rq = fnum(a.get("remain_qty"))
            if rq <= 0 or S.rsrc.get(a["rsrc_id"], {}).get("rsrc_type") == "RT_Mat":
                continue
            s = pdate(a.get("restart_date")) or t["_early_start_date"] or t["_restart_date"]
            f = pdate(a.get("reend_date")) or t["_early_end_date"] or t["_reend_date"]
            if not s or not f or f <= s:
                continue
            c = S.cal(t)
            tot = c.work_between(s, f)
            if tot <= 0:
                continue
            d = s.date()
            while d <= f.date():
                h = c.work_between(max(s, DT(d.year, d.month, d.day)), min(f, DT(d.year, d.month, d.day) + TD(days=1)))
                if h > 0:
                    load[a["rsrc_id"]][d] += rq * h / tot
                d += TD(days=1)
    rows = []
    for rid, g in sorted(agg.items(), key=lambda kv: -kv[1]["bq"]):
        r = S.rsrc.get(rid, {})
        over, peak, first = "", "", ""
        if rid in limits and load.get(rid):
            rc = S.cals.get(r.get("clndr_id")) or S.proj_cal
            days_over = []
            pk = 0.0
            for d, q in load[rid].items():
                cap = limits[rid] * (rc.day_hours(d) or rc.day_hr)
                pk = max(pk, q / cap if cap else 0)
                if q > cap + 1e-6:
                    days_over.append(d)
            over = len(days_over)
            peak = f"{pk * 100:.0f}%"
            first = fmt_d(min(days_over)) if days_over else ""
        rows.append([r.get("rsrc_short_name", rid), r.get("rsrc_name", ""), r.get("rsrc_type", "").replace("RT_", ""),
                     int(g["n"]), r1(g["bq"]), r1(g["aq"]), r1(g["rq"]), r1(g["bc"]), r1(g["ac"]), r1(g["rc"]),
                     limits.get(rid, ""), peak, over, first])
    rep = Report(f"Resources - {S.name}")
    rep.table(None, ["Resource", "Name", "Type", "Assignments", "Budget qty", "Actual qty", "Remaining qty",
                     "Budget cost", "Actual cost", "Remaining cost", "Max units/h", "Peak load", "Days over",
                     "First over"], rows,
              "Remaining quantity is spread evenly over each assignment's remaining working time; "
              "'Days over' counts days where that load exceeds the resource's max units/h x working hours.")
    return rep


def cmd_assignments(args):
    S = Schedule(args.xer, args.proj)
    rows = []
    for t in sorted(S.mine, key=lambda t: S.start(t) or DT.max):
        for a in S.assign[t["task_id"]]:
            r = S.rsrc.get(a["rsrc_id"], {})
            if args.rsrc and args.rsrc.lower() not in (r.get("rsrc_name", "") + r.get("rsrc_short_name", "")).lower():
                continue
            rows.append([t["task_code"], t["task_name"], r.get("rsrc_short_name", a["rsrc_id"]),
                         r1(fnum(a.get("target_qty"))), r1(fnum(a.get("act_reg_qty")) + fnum(a.get("act_ot_qty"))),
                         r1(fnum(a.get("remain_qty"))), r1(fnum(a.get("target_cost"))),
                         r1(fnum(a.get("act_reg_cost")) + fnum(a.get("act_ot_cost"))), r1(fnum(a.get("remain_cost")))])
    rep = Report(f"Resource assignments - {S.name}")
    rep.table(None, ["Code", "Activity", "Resource", "Budget qty", "Actual qty", "Remaining qty", "Budget cost",
                     "Actual cost", "Remaining cost"], rows[:args.limit],
              f"{len(rows)} assignments" + (f" (first {args.limit} shown)" if len(rows) > args.limit else ""))
    return rep


def cmd_longest_path(args):
    S = Schedule(args.xer, args.proj)
    path, drivers, roots, ends = S.longest_path(args.to)
    rep = Report(f"Longest (driving) path - {S.name}")
    p6 = {t["task_id"] for t in S.mine if t.get("driving_path_flag") == "Y" and not S.is_complete(t)}
    mine = {t["task_id"] for t in path}
    tf0 = [t for t in S.mine if not S.is_complete(t) and t["task_type"] not in SUMMARY
           and S.tf_days(t) is not None and S.tf_days(t) <= 0]
    kv = [("Data date", fmt_dt(S.data_date)),
          ("Traced back from", ", ".join(f"{t['task_code']} {t['task_name']} (finish {fmt_dt(S.finish(t))})" for t in ends)),
          ("Activities on path", len(path)),
          ("For contrast: incomplete activities with TF <= 0", f"{len(tf0)} (what a float-only 'critical path' would list)"),
          ("Path starts from", "; ".join(sorted(set(roots.values()))) or "")]
    if p6 and not args.to:
        kv.append(("Agreement with P6 longest-path flags",
                   f"{len(mine & p6)} in both, {len(mine - p6)} only here, {len(p6 - mine)} only in P6"
                   + ("" if (mine == p6) else " (P6 flags reflect the last 'longest path' run; differences "
                      "usually mean the schedule was recalculated without it, or ties)")))
    rep.kv("Summary", kv)
    rows = []
    for t in path:
        drv = drivers.get(t["task_id"], [])
        by = "; ".join(f"{S.task[r['pred_task_id']]['task_code']} ({RELTYPE.get(r['pred_type'])}"
                       + (f" lag {r1(S.days(S.task[r['pred_task_id']], fnum(r['lag_hr_cnt'])))}" if fnum(r['lag_hr_cnt']) else "")
                       + ")" for r in drv) or roots.get(t["task_id"], "")
        rows.append(act_row(S, t, [r1(S.days(t, fnum(t["remain_drtn_hr_cnt"]))), S.cal(t).name, by,
                                   ("Y" if t["task_id"] in p6 else "") if p6 else ""]))
    rep.table("Path (earliest first)", ACT_HDR + ["Rem dur (wd)", "Calendar", "Driven by", "P6 flag"], rows)
    if args.near is not None:
        near = sorted([t for t in S.mine if not S.is_complete(t) and t["task_id"] not in mine
                       and t["task_type"] not in SUMMARY and S.tf_days(t) is not None
                       and S.tf_days(t) <= min((S.tf_days(x) or 0) for x in path) + args.near],
                      key=lambda t: (S.tf_days(t), S.start(t) or DT.max))
        rep.table(f"Near-longest (within {args.near:g} wd of the path's float)", ACT_HDR, [act_row(S, t) for t in near[:200]],
                  f"{len(near)} activities" + (" (first 200)" if len(near) > 200 else ""))
    return rep


def cmd_float_paths(args):
    S = Schedule(args.xer, args.proj)
    groups = defaultdict(list)
    for t in S.mine:
        if t.get("float_path"):
            groups[int(fnum(t["float_path"]))].append(t)
    rep = Report(f"Multiple float paths - {S.name}")
    if not groups:
        rep.text(None, "This XER carries no float-path numbers. In P6: Schedule > Options > Advanced > "
                       "'Calculate multiple float paths', then reschedule and re-export. `longest-path` works regardless.")
        return rep
    key = S.opts.get("key_activity_for_multiple_longest_paths", "")
    kt = S.task.get(key)
    rep.kv("Settings", [("Ending activity", f"{kt['task_code']} {kt['task_name']}" if kt else
                         (f"task id {key} (not in this export; P6 kept the setting from an earlier copy)" if key
                          else "project finish")),
                        ("Paths calculated", len(groups)),
                        ("Ranked by", "total float" if S.opts.get("use_total_float_multiple_longest_paths") == "Y"
                         else "free float (driving relationships)")])
    for n in sorted(groups):
        ts = sorted(groups[n], key=lambda t: (fnum(t.get("float_path_order")), S.start(t) or DT.max))
        rep.table(f"Path {n} ({len(ts)} activities, min TF {r1(min((S.tf_days(t) or 0) for t in ts))} wd)",
                  ACT_HDR, [act_row(S, t) for t in ts])
    return rep


def _baseline_map(S, BL):
    """task_code -> (bl start, bl finish, bl budget cost, bl budget qty). Falls back to planned dates."""
    out = {}
    if BL:
        for t in BL.mine:
            cost = sum(fnum(a.get("target_cost")) for a in BL.assign[t["task_id"]])
            qty = sum(fnum(a.get("target_qty")) for a in BL.assign[t["task_id"]])
            out[t["task_code"]] = (BL.start(t), BL.finish(t), cost, qty)
    else:
        for t in S.mine:
            cost = sum(fnum(a.get("target_cost")) for a in S.assign[t["task_id"]])
            qty = sum(fnum(a.get("target_qty")) for a in S.assign[t["task_id"]])
            out[t["task_code"]] = (t["_target_start_date"], t["_target_end_date"], cost, qty)
    return out


def cmd_dcma(args):
    S = Schedule(args.xer, args.proj)
    BL = Schedule(args.baseline, args.bl_proj) if args.baseline else None
    dd = S.data_date
    inc = [t for t in S.mine if not S.is_complete(t) and t["task_type"] not in SUMMARY]
    tasks = [t for t in inc if t["task_type"] not in MILESTONES]
    inc_ids = {t["task_id"] for t in inc}
    rels = [r for r in S.rels if r["task_id"] in inc_ids or r["pred_task_id"] in inc_ids]
    res = []   # (num, name, count, denom, threshold_text, pass, offenders, note)

    def pct(n, d):
        return 100.0 * n / d if d else 0.0

    # 1 logic
    ends = {t["task_id"] for t in S.default_end()}
    starts = set()
    if inc:
        first = min(S.start(t) or DT.max for t in inc)
        starts = {t["task_id"] for t in inc if (S.start(t) or DT.max) == first and not S.preds[t["task_id"]]}
    no_p = [t for t in inc if not S.preds[t["task_id"]] and t["task_id"] not in starts]
    no_s = [t for t in inc if not S.succs[t["task_id"]] and t["task_id"] not in ends]
    bad = {t["task_id"]: t for t in no_p + no_s}
    res.append((1, "Logic (missing predecessor or successor)", len(bad), len(inc), "<= 5%",
                pct(len(bad), len(inc)) <= 5, list(bad.values()),
                f"{len(no_p)} without predecessor, {len(no_s)} without successor (project start/finish excused)"))
    leads = [r for r in rels if fnum(r.get("lag_hr_cnt")) < 0]
    res.append((2, "Leads (negative lag)", len(leads), len(rels), "0%", not leads, leads, ""))
    lags = [r for r in rels if fnum(r.get("lag_hr_cnt")) > 0]
    res.append((3, "Lags (positive lag)", len(lags), len(rels), "<= 5%", pct(len(lags), len(rels)) <= 5, lags, ""))
    nonfs = [r for r in rels if r.get("pred_type") != "PR_FS"]
    res.append((4, "Relationship types (FS share)", len(rels) - len(nonfs), len(rels), ">= 90% FS",
                pct(len(rels) - len(nonfs), len(rels)) >= 90, nonfs, f"{len(nonfs)} non-FS relationships"))
    hard = [t for t in inc if t.get("cstr_type") in HARD_CSTR or t.get("cstr_type2") in HARD_CSTR]
    res.append((5, "Hard constraints", len(hard), len(inc), "<= 5%", pct(len(hard), len(inc)) <= 5, hard,
                "Start/Finish On, On or Before, Mandatory"))
    hf = [t for t in inc if (S.tf_days(t) or 0) > 44]
    res.append((6, "High float (> 44 wd)", len(hf), len(inc), "<= 5%", pct(len(hf), len(inc)) <= 5, hf, ""))
    nf = [t for t in inc if (S.tf_days(t) or 0) < 0]
    res.append((7, "Negative float", len(nf), len(inc), "0%", not nf, nf,
                f"worst {r1(min((S.tf_days(t) for t in nf), default=0))} wd" if nf else ""))
    hd = [t for t in tasks if S.days(t, fnum(t["target_drtn_hr_cnt"])) > 44]
    res.append((8, "High duration (original > 44 wd)", len(hd), len(tasks), "<= 5%", pct(len(hd), len(tasks)) <= 5, hd, ""))
    inv = []
    for t in S.mine:
        if not dd:
            break
        if (t["_act_start_date"] and t["_act_start_date"] > dd) or (t["_act_end_date"] and t["_act_end_date"] > dd):
            inv.append(t)
        elif t["status_code"] == "TK_NotStart" and t["_early_start_date"] and t["_early_start_date"] < dd:
            inv.append(t)
        elif t["status_code"] == "TK_Active" and t["_early_end_date"] and t["_early_end_date"] < dd:
            inv.append(t)
    res.append((9, "Invalid dates (actuals after / forecasts before data date)", len(inv), len(S.mine), "0%",
                not inv, inv, ""))
    nores = [t for t in tasks if fnum(t["target_drtn_hr_cnt"]) > 0 and not S.assign[t["task_id"]]]
    loaded = any(S.assign[t["task_id"]] for t in S.mine)
    res.append((10, "Resources (tasks with duration but no assignment)", len(nores), len(tasks), "0%",
                not nores, nores, "" if loaded else "schedule is not resource-loaded at all"))
    blm = _baseline_map(S, BL)
    bl_src = (f"baseline XER {os.path.basename(args.baseline)}" if BL else "planned dates (target_*) in this XER")
    due = [t for t in S.mine if t["task_type"] not in SUMMARY and t["task_code"] in blm
           and blm[t["task_code"]][1] and dd and blm[t["task_code"]][1] <= dd]
    missed = [t for t in due if not t["_act_end_date"]
              or t["_act_end_date"].date() > blm[t["task_code"]][1].date()]
    res.append((11, "Missed tasks (finished late or not at all vs baseline)", len(missed), len(due), "<= 5%",
                pct(len(missed), len(due)) <= 5, missed, f"baseline = {bl_src}"))
    path, drivers, roots, end_ts = S.longest_path()
    breaks = {r for r in roots.values() if not r.startswith(("data date", "in progress", "level of effort", "As Late"))}
    res.append((12, "Critical path test (driving chain reaches data date)", len(breaks), 1, "pass/fail",
                not breaks, [], ("path starts at: " + "; ".join(sorted(set(roots.values())))) if roots else
                "no incomplete path"))
    fin = end_ts[0] if end_ts else None
    cpli = None
    if fin and dd:
        cpl = S.proj_cal.work_between(dd, S.finish(fin)) / S.proj_cal.day_hr
        tf = S.tf_days(fin) or 0
        cpli = (cpl + tf) / cpl if cpl > 0 else None
    res.append((13, "CPLI (critical path length index)", r1(cpli) if cpli is None else round(cpli, 3), "", ">= 0.95",
                cpli is not None and cpli >= 0.95, [],
                f"CPL {r1(cpl) if fin and dd else ''} wd, finish TF {r1(S.tf_days(fin)) if fin else ''} wd" if fin else ""))
    done = [t for t in due if t["_act_end_date"]]
    completed_all = [t for t in S.mine if t["task_type"] not in SUMMARY and t["_act_end_date"] and dd
                     and t["_act_end_date"] <= dd and t["task_code"] in blm]
    bei = (len(completed_all) / len(due)) if due else None
    res.append((14, "BEI (baseline execution index)", None if bei is None else round(bei, 3), "", ">= 0.95",
                bei is not None and bei >= 0.95, [],
                f"{len(completed_all)} completed / {len(due)} due by data date ({len(done)} of the due ones finished)"))
    rep = Report(f"DCMA 14-point assessment - {S.name}")
    rep.kv("Basis", [("Data date", fmt_dt(dd)), ("Incomplete activities assessed", len(inc)),
                     ("Relationships assessed", len(rels)), ("Baseline", bl_src)])
    rows = []
    for n, name, cnt, den, thr, ok, offenders, note in res:
        val = cnt if den == "" else f"{cnt} / {den} ({pct(cnt, den):.1f}%)"
        rows.append([n, name, val, thr, "PASS" if ok else "FAIL", note])
    rep.table("Results", ["#", "Check", "Result", "Threshold", "Pass", "Notes"], rows)
    if args.details:
        for n, name, cnt, den, thr, ok, offenders, note in res:
            if ok or not offenders:
                continue
            if "task_pred_id" in offenders[0]:
                rr = [[S.task[r["pred_task_id"]]["task_code"], RELTYPE.get(r["pred_type"]), S.task[r["task_id"]]["task_code"],
                       r1(S.days(S.task[r["pred_task_id"]], fnum(r.get("lag_hr_cnt"))))] for r in offenders[:args.details]]
                rep.table(f"#{n} {name} - first {min(args.details, len(offenders))}", ["Pred", "Type", "Succ", "Lag (wd)"], rr)
            else:
                rep.table(f"#{n} {name} - first {min(args.details, len(offenders))}", ACT_HDR,
                          [act_row(S, t) for t in offenders[:args.details]])
    return rep


def cmd_earned_value(args):
    S = Schedule(args.xer, args.proj)
    BL = Schedule(args.baseline, args.bl_proj) if args.baseline else None
    blm = _baseline_map(S, BL)
    bl_budgets = bool(BL) and any(BL.assign[t["task_id"]] for t in BL.mine)
    missing_bl = sum(1 for t in S.mine if BL and t["task_code"] not in blm and t["task_type"] not in SUMMARY)
    dd = S.data_date
    tot = Counter()
    by_wbs = defaultdict(Counter)
    for t in S.mine:
        if t["task_type"] in SUMMARY:
            continue
        a = S.assign[t["task_id"]]
        bac = sum(fnum(x.get("target_cost")) for x in a)
        bq = sum(fnum(x.get("target_qty")) for x in a)
        ac = sum(fnum(x.get("act_reg_cost")) + fnum(x.get("act_ot_cost")) for x in a)
        aq = sum(fnum(x.get("act_reg_qty")) + fnum(x.get("act_ot_qty")) for x in a)
        etc = sum(fnum(x.get("remain_cost")) for x in a)
        if S.is_complete(t):
            pc = 1.0
        elif t.get("complete_pct_type") == "CP_Drtn":
            od = fnum(t["target_drtn_hr_cnt"])
            pc = max(0.0, (od - fnum(t["remain_drtn_hr_cnt"])) / od) if od else 0.0
        elif t.get("complete_pct_type") == "CP_Units":
            pc = aq / (aq + sum(fnum(x.get("remain_qty")) for x in a)) if (aq or bq) else 0.0
        else:
            pc = fnum(t.get("phys_complete_pct")) / 100.0
        etq = sum(fnum(x.get("remain_qty")) for x in a)
        bs, bf, blc, blq = blm.get(t["task_code"], (None, None, bac, bq))
        if not bl_budgets:      # no baseline, or a baseline without resource budgets
            blc, blq = bac, bq
        frac = 0.0
        if bs and bf and dd:
            if dd >= bf:
                frac = 1.0
            elif dd > bs:
                c = S.cal(t)
                span = c.work_between(bs, bf)
                frac = (c.work_between(bs, dd) / span) if span > 0 else 1.0
        row = Counter(BAC=blc, PV=blc * frac, EV=blc * pc, AC=ac, ETC=etc,
                      BACq=blq, PVq=blq * frac, EVq=blq * pc, ACq=aq, ETCq=etq)
        tot.update(row)
        top = S.wbs_path(t["wbs_id"]).split(".")[0]
        tw = next((w for w in S.wbs.values() if w["proj_id"] == S.proj_id and w["wbs_short_name"] == top
                   and S.wbs.get(w.get("parent_wbs_id"), {}).get("proj_node_flag") == "Y"), None)
        by_wbs[f"{top} {tw['wbs_name']}" if tw else (top or "(root)")].update(row)

    def metrics(c, unit=""):
        q = "" if unit == "" else "q"
        b, pv, ev, ac, etc_ = (c["BAC" + q], c["PV" + q], c["EV" + q], c["AC" + q], c["ETC" + q])
        cpi = ev / ac if ac else None
        spi = ev / pv if pv else None
        return [r1(b), r1(pv), r1(ev), r1(ac), r1(ev - ac), r1(ev - pv),
                None if cpi is None else round(cpi, 3), None if spi is None else round(spi, 3),
                r1(b / cpi) if cpi else None, r1(ac + etc_)]

    rep = Report(f"Earned value - {S.name}")
    if BL:
        bl_txt = f"baseline XER {os.path.basename(args.baseline)} (dates" + (
            " and budgets)" if bl_budgets else "; it has no resource budgets, so current budgets are used)")
        if missing_bl:
            bl_txt += f"; {missing_bl} activities are not in the baseline (no PV)"
    else:
        bl_txt = "planned dates and budgets in this XER (pass --baseline for a true baseline)"
    rep.kv("Basis", [("Data date", fmt_dt(dd)),
                     ("Baseline", bl_txt),
                     ("Method", "EV = baseline budget x % complete; PV = baseline budget x share of baseline "
                                "working time elapsed at the data date (linear spread)")])
    hdr = ["Scope", "BAC", "PV", "EV", "AC", "CV", "SV", "CPI", "SPI", "EAC (BAC/CPI)", "EAC (AC+ETC)"]
    if tot["BAC"] or tot["AC"]:
        rep.table("Cost", hdr, [["Project"] + metrics(tot)] +
                  [[k] + metrics(v) for k, v in sorted(by_wbs.items()) if v["BAC"] or v["AC"]])
    if tot["BACq"] or tot["ACq"]:
        rep.table("Units (hours/quantity)", hdr, [["Project"] + metrics(tot, "q")] +
                  [[k] + metrics(v, "q") for k, v in sorted(by_wbs.items()) if v["BACq"] or v["ACq"]])
    if not (tot["BAC"] or tot["AC"] or tot["BACq"] or tot["ACq"]):
        rep.text(None, "No budgeted cost or units on resource assignments; earned value needs a resource/cost-loaded schedule.")
    return rep


def cmd_diff(args):
    A = Schedule(args.old, args.proj)
    B = Schedule(args.new, args.new_proj or args.proj)
    ca, cb = A.by_code, B.by_code
    rep = Report(f"Schedule comparison - {A.name} -> {B.name}")
    fa, fb = A.finish_date(), B.finish_date()
    cal = B.proj_cal

    def wd(a, b):
        return None if not (a and b) else r1(cal.work_between(a, b) / cal.day_hr)

    def cd(a, b):
        return None if not (a and b) else round((b - a).total_seconds() / 86400.0, 1)

    added = sorted(set(cb) - set(ca))
    deleted = sorted(set(ca) - set(cb))
    common = sorted(set(ca) & set(cb))
    rep.kv("Headline", [
        ("Old", f"{os.path.basename(A.path)} - data date {fmt_dt(A.data_date)}"),
        ("New", f"{os.path.basename(B.path)} - data date {fmt_dt(B.data_date)}"),
        ("Forecast finish", f"{fmt_dt(fa)} -> {fmt_dt(fb)}  ({wd(fa, fb):+} wd / {cd(fa, fb):+} cd)" if fa and fb else ""),
        ("Data date advanced", f"{cd(A.data_date, B.data_date)} cd" if A.data_date and B.data_date else ""),
        ("Activities", f"{len(ca)} -> {len(cb)} ({len(added)} added, {len(deleted)} deleted)"),
    ])

    # milestones
    rows = []
    for c in common:
        a, b = ca[c], cb[c]
        if b["task_type"] in MILESTONES or a["task_type"] in MILESTONES:
            fa_, fb_ = A.finish(a), B.finish(b)
            v = wd(fa_, fb_)
            if v:
                rows.append([c, b["task_name"], fmt_d(fa_), fmt_d(fb_), v, r1(A.tf_days(a)), r1(B.tf_days(b))])
    rows.sort(key=lambda r: -abs(r[4] or 0))
    rep.table("Milestone movement", ["Code", "Name", "Old finish", "New finish", "Shift (wd)", "Old TF", "New TF"],
              rows[:args.top], f"{len(rows)} milestones moved" + (f" (top {args.top})" if len(rows) > args.top else ""))

    # longest path churn
    try:
        lpa = {t["task_code"] for t in A.longest_path(args.to)[0]}
        lpb = {t["task_code"] for t in B.longest_path(args.to)[0]}
        rows = [[c, (cb.get(c) or ca.get(c))["task_name"], "joined" if c in lpb else "left",
                 r1(A.tf_days(ca[c])) if c in ca else "", r1(B.tf_days(cb[c])) if c in cb else ""]
                for c in sorted(lpa ^ lpb, key=lambda c: (c not in lpb, c))]
        cap = args.top * 3
        rep.table("Longest-path changes", ["Code", "Name", "Change", "Old TF", "New TF"], rows[:cap],
                  f"Old path {len(lpa)} activities, new path {len(lpb)}; {len(lpa & lpb)} in both, "
                  f"{len(lpb - lpa)} joined, {len(lpa - lpb)} left" + (f" (first {cap} shown)" if len(rows) > cap else "") + ".")
    except XerError as e:
        rep.text("Longest-path changes", str(e))

    # progress this period
    if A.data_date and B.data_date:
        planned = [c for c in common if not A.is_complete(ca[c]) and A.finish(ca[c]) and A.finish(ca[c]) <= B.data_date
                   and ca[c]["task_type"] not in SUMMARY]
        achieved = [c for c in planned if B.is_complete(cb[c])]
        started = [c for c in common if not A.is_started(ca[c]) and B.is_started(cb[c])]
        finished = [c for c in common if not A.is_complete(ca[c]) and B.is_complete(cb[c])]
        rep.kv("Progress this period", [
            ("Planned to finish (old forecast) by new data date", len(planned)),
            ("...of which actually finished", f"{len(achieved)}" + (f" ({100.0 * len(achieved) / len(planned):.0f}%)" if planned else "")),
            ("Started this period", len(started)), ("Finished this period", len(finished))])
        got = set(achieved)
        miss = [c for c in planned if c not in got]
        rep.table("Planned to finish this period but did not", ["Code", "Name", "Old finish", "New finish", "Status"],
                  [[c, cb[c]["task_name"], fmt_d(A.finish(ca[c])), fmt_d(B.finish(cb[c])),
                    STATUS.get(cb[c]["status_code"])] for c in miss[:args.top]],
                  f"{len(miss)} activities" + (f" (first {args.top})" if len(miss) > args.top else ""))

    # retroactive actuals
    rows = []
    for c in common:
        a, b = ca[c], cb[c]
        for k, lbl in (("_act_start_date", "actual start"), ("_act_end_date", "actual finish")):
            if a[k] and a[k] != b[k]:
                rows.append([c, b["task_name"], lbl, fmt_dt(a[k]), fmt_dt(b[k]) or "(removed)"])
        if A.is_complete(a) and not B.is_complete(b):
            rows.append([c, b["task_name"], "status", "Complete", STATUS.get(b["status_code"])])
    rep.table("Actuals changed after the fact", ["Code", "Name", "Field", "Old", "New"], rows,
              "Actual dates recorded in the old update that differ in the new one. In a forensic review these need an explanation.")

    # slips
    rows = []
    for c in common:
        a, b = ca[c], cb[c]
        if B.is_complete(b) or b["task_type"] in SUMMARY:
            continue
        v = wd(A.finish(a), B.finish(b))
        if v and abs(v) >= 0.5:
            rows.append([c, b["task_name"], fmt_d(A.finish(a)), fmt_d(B.finish(b)), v,
                         r1(A.tf_days(a)), r1(B.tf_days(b)), r1((B.tf_days(b) or 0) - (A.tf_days(a) or 0))])
    rows.sort(key=lambda r: -(r[4] or 0))
    rep.table("Largest finish slips (incomplete activities)",
              ["Code", "Name", "Old finish", "New finish", "Shift (wd)", "Old TF", "New TF", "TF change"],
              rows[:args.top], f"{len(rows)} activities moved >= 0.5 wd" + (f" (top {args.top})" if len(rows) > args.top else ""))

    # structural edits
    dur, cons, cals, names, types = [], [], [], [], []
    for c in common:
        a, b = ca[c], cb[c]
        oa, ob = A.days(a, fnum(a["target_drtn_hr_cnt"])), B.days(b, fnum(b["target_drtn_hr_cnt"]))
        if abs(oa - ob) >= 0.05:
            dur.append([c, b["task_name"], r1(oa), r1(ob), r1(ob - oa), STATUS.get(b["status_code"])])
        ka = (a.get("cstr_type", ""), fmt_d(a["_cstr_date"]), a.get("cstr_type2", ""), fmt_d(a["_cstr_date2"]))
        kb = (b.get("cstr_type", ""), fmt_d(b["_cstr_date"]), b.get("cstr_type2", ""), fmt_d(b["_cstr_date2"]))
        if ka != kb:
            fmtc = lambda k: "; ".join(f"{CSTR.get(k[i], k[i])} {k[i + 1]}" for i in (0, 2) if k[i]) or "none"
            cons.append([c, b["task_name"], fmtc(ka), fmtc(kb)])
        if A.cal(a).name != B.cal(b).name:
            cals.append([c, b["task_name"], A.cal(a).name, B.cal(b).name])
        if a["task_name"] != b["task_name"]:
            names.append([c, a["task_name"], b["task_name"]])
        if a["task_type"] != b["task_type"]:
            types.append([c, b["task_name"], TTYPE.get(a["task_type"]), TTYPE.get(b["task_type"])])
    dur.sort(key=lambda r: -abs(r[4] or 0))
    rep.table("Original duration changes", ["Code", "Name", "Old (wd)", "New (wd)", "Change", "Status"], dur[:args.top],
              f"{len(dur)} activities" + (f" (top {args.top})" if len(dur) > args.top else ""))
    rep.table("Constraint changes", ["Code", "Name", "Old", "New"], cons)
    rep.table("Calendar changes", ["Code", "Name", "Old", "New"], cals)
    rep.table("Activity type changes", ["Code", "Name", "Old", "New"], types)
    rep.table("Renamed activities", ["Code", "Old name", "New name"], names[:args.top],
              f"{len(names)} renamed" + (f" (first {args.top})" if len(names) > args.top else ""))

    # logic
    def relmap(S):
        m = {}
        for r in S.rels:
            p, s = S.task[r["pred_task_id"]], S.task[r["task_id"]]
            if s["proj_id"] == S.proj_id or p["proj_id"] == S.proj_id:
                m[(p["task_code"], s["task_code"], r["pred_type"])] = r1(S.days(p, fnum(r.get("lag_hr_cnt"))))
        return m

    ra, rb = relmap(A), relmap(B)
    pairs_a = defaultdict(dict)
    pairs_b = defaultdict(dict)
    for (p, s, ty), lag in ra.items():
        pairs_a[(p, s)][ty] = lag
    for (p, s, ty), lag in rb.items():
        pairs_b[(p, s)][ty] = lag
    lrows = []
    for k in sorted(set(pairs_a) | set(pairs_b)):
        x, y = pairs_a.get(k, {}), pairs_b.get(k, {})
        if x == y:
            continue
        fx = ", ".join(f"{RELTYPE.get(t)} {l:+g}" if l else RELTYPE.get(t, t) for t, l in sorted(x.items())) or "-"
        fy = ", ".join(f"{RELTYPE.get(t)} {l:+g}" if l else RELTYPE.get(t, t) for t, l in sorted(y.items())) or "-"
        kind = "added" if not x else ("deleted" if not y else "changed")
        lrows.append([k[0], k[1], kind, fx, fy])
    lc = Counter(r[2] for r in lrows)
    rep.table("Logic changes", ["Pred", "Succ", "Change", "Old (type lag wd)", "New"], lrows[:args.top * 3],
              f"{lc['added']} added, {lc['deleted']} deleted, {lc['changed']} changed (type or lag)"
              + (f"; first {args.top * 3} shown" if len(lrows) > args.top * 3 else ""))
    rep.table("Added activities", ["Code", "Name", "Start", "Finish", "Orig dur (wd)"],
              [[c, cb[c]["task_name"], fmt_d(B.start(cb[c])), fmt_d(B.finish(cb[c])),
                r1(B.days(cb[c], fnum(cb[c]["target_drtn_hr_cnt"])))] for c in added])
    rep.table("Deleted activities", ["Code", "Name", "Status in old", "Old finish"],
              [[c, ca[c]["task_name"], STATUS.get(ca[c]["status_code"]), fmt_d(A.finish(ca[c]))] for c in deleted])
    return rep


# ------------------------------------------------------------- milestone gaps
GAP_GROUP_RE = r"^\s*([A-Za-z][A-Za-z .&/-]*?\s*\d+[A-Za-z]?)\s*[:\-–]\s"
GAP_KEY_RE = r"\(([A-Za-z][A-Za-z0-9&/]{1,9})\)"
GAP_WBS_RE = r"^\s*([A-Za-z][A-Za-z .&/-]{0,20}?[\s_-]*\d+[A-Za-z]?)\s*$"     # a WBS node "ROMP 01"
GAP_CODE_RE = r"((?:ROMP|PHASE|PH|AREA|BLDG|ZONE|SECTOR|DH|POD)[-_ ]?\d+[A-Za-z]?)(?![0-9])"


def _norm_group(s):
    """'ROMP 01' / 'ROMP-1' / 'romp1' -> 'ROMP 1' so versions and CSVs line up."""
    m = re.match(r"^(.*?)[\s_-]*0*(\d+)([A-Za-z]?)$", s.strip())
    return f"{m.group(1).strip().upper()} {m.group(2)}{m.group(3).upper()}" if m else s.strip()


def _natkey(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def _parse_any_date(s):
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):                       # Excel serial
        return EXCEL_EPOCH + TD(days=int(float(s)))
    for f in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return DT.strptime(s, f).date()
        except ValueError:
            pass
    raise XerError(f"unrecognised date {s!r} (use YYYY-MM-DD or MM/DD/YYYY)")


def _gap_version(path, args, grp_re, key_re):
    """-> (label, {(group, key): (date, code, name)}, Schedule or None, notes)."""
    notes = []
    found = {}
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        cols = {c.lower().strip(): c for c in (rows[0].keys() if rows else [])}
        need = [c for c in ("group", "milestone", "date") if c not in cols]
        if need:
            raise XerError(f"{os.path.basename(path)}: CSV needs columns Group, Milestone, Date")
        for r in rows:
            d = _parse_any_date(r[cols["date"]])
            if d:
                found[(_norm_group(r[cols["group"]]), r[cols["milestone"]].strip())] = (d, "", "manual")
        return os.path.splitext(os.path.basename(path))[0], found, None, notes
    S = Schedule(path, args.proj)
    for t in sorted(S.mine, key=lambda t: t["task_code"]):
        if t["task_type"] not in MILESTONES and not args.all_types:
            continue
        name = t["task_name"]
        if args.search and args.search.lower() not in name.lower():
            continue
        k = re.findall(key_re, name)
        if not k:
            continue
        g = re.search(grp_re, name)
        if not g:   # phase not in the name: try the WBS (deepest node first), then the code
            nodes = list(reversed(S.wbs_path(t["wbs_id"], names=True).split(" > ")))
            g = next((m for n in nodes for m in [re.search(args.group or GAP_WBS_RE, n)] if m), None)
        if not g:
            g = re.search(args.group or GAP_CODE_RE, t["task_code"], re.I)
        if not g:
            continue
        key = (_norm_group(g.group(1)), k[-1] if args.key == GAP_KEY_RE else k[0])
        d = S.start(t) if t["task_type"] == "TT_Mile" else S.finish(t)
        if not d:
            continue
        if key in found:
            notes.append(f"{os.path.basename(path)}: {key[0]} {key[1]} matched both "
                         f"{found[key][1]} and {t['task_code']}; kept {found[key][1]}")
            continue
        found[key] = (d.date(), t["task_code"], name)
    return os.path.splitext(os.path.basename(path))[0], found, S, notes


def cmd_gaps(args):
    grp_re, key_re = args.group or GAP_GROUP_RE, args.key or GAP_KEY_RE
    args.key = key_re
    versions, notes, cal = [], [], None
    for p in args.files:
        label, found, S, n = _gap_version(p, args, grp_re, key_re)
        notes += n
        if S is not None and cal is None:
            cal = S.proj_cal
        versions.append([label, found, S])
    if args.labels:
        labels = [x.strip() for x in args.labels.split(",")]
        if len(labels) != len(versions):
            raise XerError(f"--labels has {len(labels)} names for {len(versions)} files")
        for v, l in zip(versions, labels):
            v[0] = l
    names = [v[0] for v in versions]

    def pick(lbl, default):
        if not lbl:
            return default
        m = [i for i, n in enumerate(names) if n.lower() == lbl.lower()]
        if not m:
            raise XerError(f"no version labelled {lbl!r}; versions: {', '.join(names)}")
        return m[0]
    ref, foc = pick(args.ref, 0), pick(args.focus, len(versions) - 1)

    groups = sorted({g for v in versions for g, _ in v[1]}, key=_natkey)
    if not groups:
        raise XerError("no milestones matched. Names must look like 'ROMP 3: Network Early Access "
                       "(NEA)'; set --group / --key regexes (one capture group each) for other naming")
    if args.keys:
        keys = [k.strip() for k in args.keys.split(",")]
    else:
        # Order milestone types by pairwise majority (Copeland): a precedes b when, in most
        # groups holding both, a's date is earlier. Robust to types that occur in one group only.
        allk = sorted({k for v in versions for _, k in v[1]})
        votes = Counter()
        for v in versions:
            for g in groups:
                have = {k: d for (gg, k), (d, _, _) in v[1].items() if gg == g}
                for a in have:
                    for b in have:
                        if a != b and have[a] < have[b]:
                            votes[(a, b)] += 1
        score = {a: sum(1 for b in allk if votes[(a, b)] > votes[(b, a)]) for a in allk}
        keys = sorted(allk, key=lambda k: (-score[k], k))
        args.keys_inferred = True
    if not cal and args.workdays:
        raise XerError("--workdays needs at least one .xer input (for its calendar)")
    unit = "wd" if args.workdays else "cd"

    def span(a, b):
        if a is None or b is None:
            return None
        if not args.workdays:
            return (b - a).days
        da, db = DT.combine(a, _dt.time()), DT.combine(b, _dt.time())
        sign = 1 if db >= da else -1
        lo, hi = min(da, db), max(da, db)
        return sign * r1(cal.work_between(lo, hi) / (cal.day_hr or 8.0))

    def date_of(vi, g, k):
        x = versions[vi][1].get((g, k))
        return x[0] if x else None

    # gap definitions: stagger between consecutive groups, then steps inside a group
    gap_defs, prev_key = [], {}
    for gi, g in enumerate(groups):
        for k in keys:
            if gi:
                gap_defs.append((g, f"{k} stagger (vs {groups[gi - 1]})", (groups[gi - 1], k), (g, k)))
        present = [k for k in keys if any((g, k) in v[1] for v in versions)]
        for k1, k2 in zip(present, present[1:]):     # step from the previous milestone this group has
            prev_key[(g, k2)] = k1
            gap_defs.append((g, f"{k1} to {k2}", (g, k1), (g, k2)))
    gval = {}
    for vi in range(len(versions)):
        for g, lbl, a, b in gap_defs:
            gval[(vi, g, lbl)] = span(date_of(vi, *a), date_of(vi, *b))

    rep = Report(f"Milestone gap check - {names[foc]} vs {names[ref]}")
    rep.kv("Basis", [
        ("Versions", ", ".join(f"{n} ({os.path.basename(p)})" for n, p in zip(names, args.files))),
        ("Reference", names[ref]), ("Analysed", names[foc]),
        ("Groups", f"{len(groups)} ({groups[0]} .. {groups[-1]})"),
        ("Milestones per group", ", ".join(keys) + (
            " (order inferred from the dates; set it with --keys, e.g. --keys NEA,H2C,PFHO)"
            if getattr(args, "keys_inferred", False) else "")),
        ("Units", "working days on the project calendar" if args.workdays else "calendar days"),
        ("Gap", "stagger = same milestone in the previous group; step = previous milestone in the "
                "same group. Change = analysed - reference; negative = the gap was squeezed."),
    ])

    # 1) the Excel-style sheet: dates by version, delta, and the analysed version's gaps
    hdr = ["Group", "Milestone", "Code"] + names + [f"Delta {names[foc]} vs {names[ref]} ({unit})"]
    hdr += [f"Stagger ({unit})", f"Step from previous ({unit})"]
    rows = []
    for gi, g in enumerate(groups):
        for ki, k in enumerate(keys):
            code = next((v[1][(g, k)][1] for v in (versions[foc], versions[ref], *versions)
                         if (g, k) in v[1] and v[1][(g, k)][1]), "")
            ds = [date_of(vi, g, k) for vi in range(len(versions))]
            if not any(ds):
                continue
            stag = gval.get((foc, g, f"{k} stagger (vs {groups[gi - 1]})")) if gi else None
            step = gval.get((foc, g, f"{prev_key[(g, k)]} to {k}")) if (g, k) in prev_key else None
            rows.append([g, k, code] + [fmt_d(d) if d else "-" for d in ds]
                        + [span(ds[ref], ds[foc]), stag, step])
    rep.table("Milestone dates and gaps", hdr, rows,
              note=f"Stagger and step columns are for {names[foc]}.")

    # 2) every gap, every version
    rows, squeezed, flags = [], [], []
    for g, lbl, a, b in gap_defs:
        vals = [gval[(vi, g, lbl)] for vi in range(len(versions))]
        if all(v is None for v in vals):
            continue
        r_, f_ = vals[ref], vals[foc]
        chg = None if r_ is None or f_ is None else r1(f_ - r_)
        pct = None if chg is None or not r_ else round(100.0 * chg / abs(r_))
        rows.append([g, lbl] + vals + [chg, pct])
        if chg is not None and chg < 0:
            squeezed.append([g, lbl, r_, f_, chg, pct])
        why = []
        if f_ is not None and f_ <= 0:
            why.append(("out of sequence" if f_ < 0 else "no gap")
                       + (f" (already so in {names[ref]})" if r_ is not None and r_ <= 0 else " (new)"))
        if args.min_gap is not None and f_ is not None and 0 < f_ < args.min_gap:
            why.append(f"under {args.min_gap:g} {unit}")
        if args.shrink is not None and chg is not None and -chg >= args.shrink:
            why.append(f"squeezed {-chg:g} {unit}")
        if why:
            flags.append([g, lbl, r_, f_, chg, "; ".join(why)])
    rep.table("All gaps by version", ["Group", "Gap"] + names + [f"Change ({unit})", "Change %"], rows)
    squeezed.sort(key=lambda r: (r[4], _natkey(r[0])))
    rep.table(f"Squeezed gaps ({names[foc]} tighter than {names[ref]})",
              ["Group", "Gap", names[ref], names[foc], f"Change ({unit})", "Change %"], squeezed,
              note="Less room between handovers than the reference allowed: crews, commissioning "
                   "and the owner have to absorb overlap here.")
    rep.table("Flags", ["Group", "Gap", names[ref], names[foc], f"Change ({unit})", "Why"], flags,
              note="Out-of-sequence or zero gaps always flag; add --min-gap N / --shrink N for "
                   "thresholds.")

    # 3) roll-up per gap type: is the cadence holding?
    rollup = []
    steps = list(dict.fromkeys(l for _, l, _, _ in gap_defs if " to " in l and "stagger" not in l))
    for lbl_kind in [f"{k} stagger" for k in keys] + steps:
        def series(vi):
            return [gval[(vi, g, l)] for g, l, _, _ in gap_defs
                    if l.startswith(lbl_kind) and gval[(vi, g, l)] is not None]
        sr, sf = series(ref), series(foc)
        if not sr and not sf:
            continue
        stat = lambda s: f"{min(s):g} / {r1(sum(s) / len(s)):g} / {max(s):g}" if s else "-"
        rollup.append([lbl_kind, stat(sr), stat(sf)])
    rep.table("Cadence summary (min / mean / max)", ["Gap type", names[ref], names[foc]], rollup)

    anywhere = {gk for v in versions for gk in v[1]}
    missing = [[n, g, k] for n, v in zip(names, versions) for g in groups for k in keys
               if (g, k) in anywhere and (g, k) not in v[1]]
    if missing:
        rep.table("Missing from a version", ["Version", "Group", "Milestone"], missing[:200],
                  note="Present in another version but not matched in this one (deleted or renamed).")
    if notes:
        rep.text("Notes", "\n".join(f"- {n}" for n in notes))
    return rep


def cmd_export(args):
    tables, _ = read_xer(args.xer)
    want = [t.strip().upper() for t in args.tables.split(",")] if args.tables else list(tables)
    os.makedirs(args.out_dir, exist_ok=True)
    rep = Report(f"Export of {os.path.basename(args.xer)}")
    rows = []
    for name in want:
        if name not in tables:
            rows.append([name, "missing", ""])
            continue
        data = tables[name]
        fields = list(data[0].keys()) if data else []
        p = os.path.join(args.out_dir, name + ".csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(fields)
            for r in data:
                w.writerow([r.get(k, "").replace("\x7f\x7f", "\n") for k in fields])
        rows.append([name, len(data), p])
    rep.table(None, ["Table", "Rows", "File"], rows)
    return rep


def text_summary(path):
    """Plain-text digest used by extract_text.py when it meets an .xer."""
    out = []
    tables, _ = read_xer(path)
    for p in tables["PROJECT"]:
        try:
            S = Schedule(path, p["proj_id"])
        except XerError:
            continue
        if not S.mine:
            continue
        out.append(cmd_summary(argparse.Namespace(xer=path, proj=p["proj_id"])).markdown())
        lp = cmd_longest_path(argparse.Namespace(xer=path, proj=p["proj_id"], to=None, near=None))
        out.append(lp.markdown())
    return "\n\n".join(out)


# ========================================================================= CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog="xer_tool.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--proj", help="project short name or id (default: export-flagged / largest)")
    common.add_argument("--json", action="store_true")
    common.add_argument("--out", help="also write the Markdown report here")
    common.add_argument("--csv", help="also write each report table as CSV into this folder")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *pos):
        p = sub.add_parser(name, parents=[common])
        for a in pos:
            p.add_argument(a)
        p.set_defaults(fn=fn)
        return p

    add("projects", cmd_projects, "xer")
    add("summary", cmd_summary, "xer")
    p = add("activities", cmd_activities, "xer")
    p.add_argument("--status", choices=["not_started", "active", "complete", "incomplete"])
    p.add_argument("--type", choices=["task", "milestone", "loe", "wbs"])
    p.add_argument("--wbs")
    p.add_argument("--search")
    p.add_argument("--float-lt", type=float, dest="float_lt")
    p.add_argument("--longest-path", action="store_true", dest="longest_path")
    p.add_argument("--limit", type=int, default=500)
    add("activity", cmd_activity, "xer", "code")
    p = add("wbs", cmd_wbs, "xer")
    p.add_argument("--depth", type=int)
    p = add("relationships", cmd_relationships, "xer")
    p.add_argument("--code")
    p.add_argument("--limit", type=int, default=500)
    p = add("calendars", cmd_calendars, "xer")
    p.add_argument("--holidays", type=int)
    add("resources", cmd_resources, "xer")
    p = add("assignments", cmd_assignments, "xer")
    p.add_argument("--rsrc")
    p.add_argument("--limit", type=int, default=500)
    p = add("longest-path", cmd_longest_path, "xer")
    p.add_argument("--to", help="trace back from this activity code instead of the project finish")
    p.add_argument("--near", type=float, help="also list activities within N wd of the path's float")
    add("float-paths", cmd_float_paths, "xer")
    p = add("dcma", cmd_dcma, "xer")
    p.add_argument("--baseline")
    p.add_argument("--bl-proj", dest="bl_proj")
    p.add_argument("--details", type=int, default=0, help="list up to N offenders per failed check")
    p = add("earned-value", cmd_earned_value, "xer")
    p.add_argument("--baseline")
    p.add_argument("--bl-proj", dest="bl_proj")
    p = add("diff", cmd_diff, "old", "new")
    p.add_argument("--new-proj", dest="new_proj", help="project in the new file if its name differs")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--to", help="compare longest paths to this activity code")
    p = sub.add_parser("gaps", parents=[common],
                       help="milestone gap check across schedule versions (TIA, rebaseline, mitigation)")
    p.add_argument("files", nargs="+", help=".xer files and/or Group,Milestone,Date .csv files, oldest first")
    p.add_argument("--labels", help="comma list of names for the versions, in file order")
    p.add_argument("--ref", help="reference version label (default: the first)")
    p.add_argument("--focus", help="version to analyse (default: the last)")
    p.add_argument("--keys", help="milestone order inside a group, e.g. NEA,H2C,PFHO (default: inferred)")
    p.add_argument("--group", help="regex with one capture group for the phase, from the activity name")
    p.add_argument("--key", help="regex with one capture group for the milestone type")
    p.add_argument("--search", help="only milestones whose name contains this text")
    p.add_argument("--all-types", action="store_true", dest="all_types",
                   help="match tasks too, not only milestones")
    p.add_argument("--workdays", action="store_true", help="gaps in working days, not calendar days")
    p.add_argument("--min-gap", type=float, dest="min_gap", help="flag gaps shorter than N")
    p.add_argument("--shrink", type=float, help="flag gaps squeezed by N or more vs the reference")
    p.set_defaults(fn=cmd_gaps)
    p = add("export", cmd_export, "xer", "out_dir")
    p.add_argument("--tables", help="comma list, e.g. TASK,TASKPRED (default: all)")

    args = ap.parse_args(argv)
    try:
        rep = args.fn(args)
    except XerError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    md = rep.markdown()
    print(rep.as_json() if args.json else md)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md + "\n")
    if args.csv:
        n = rep.write_csv(args.csv)
        print(f"\n({n} CSV tables written to {args.csv})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
