"""Entry replacement exports preserving the original FanDuel template."""
import csv
import io
import re


def build_fanduel_entry_export(template, portfolio, player_ids, contest, mode):
    text = template.decode("utf-8-sig") if isinstance(template, bytes) else template
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("The FanDuel entry template is empty.")
    header = [str(c).strip().casefold() for c in rows[0]]
    def column(aliases):
        return next((i for i,c in enumerate(header) if c in aliases), None)
    entry = column({"entry_id","entry id","entryid"})
    contest_col = column({"contest_id","contest id","contestid"})
    if entry is None or contest_col is None:
        raise ValueError("Upload the original FanDuel entries template with Entry ID and Contest ID.")
    single = mode == "Single Game"
    slots = ["MVP","FLEX1","FLEX2","FLEX3","FLEX4","FLEX5"] if single else ["QB","RB1","RB2","WR1","WR2","WR3","TE","FLEX","D"]
    aliases = ([{"mvp","mvp - 1.5x points"}]+[{"anyflex","flex"}]*5 if single else
               [{"qb"},{"rb"},{"rb"},{"wr"},{"wr"},{"wr"},{"te"},{"flex"},{"d","def","dst"}])
    used = set()
    indices = []
    for slot, options in zip(slots, aliases):
        idx = next((i for i,c in enumerate(header) if c in options and i not in used), None)
        if idx is None:
            raise ValueError(f"The FanDuel template has no column for {slot}. Check the roster format.")
        used.add(idx); indices.append(idx)
    target = str(contest.get("id","")).strip()
    targets = []
    for i,row in enumerate(rows[1:],1):
        if not row or not row[0].strip():
            break
        if len(row)>contest_col and row[contest_col].strip()==target:
            targets.append(i)
    if not targets:
        raise ValueError("No reserved entries match the selected FanDuel contest.")
    identifiers = [rows[i][entry].strip() for i in targets]
    if any(not re.fullmatch(r"[1-9]\d*",v) for v in identifiers) or len(set(identifiers))!=len(identifiers):
        raise ValueError("Reserved Entry IDs must be unique positive integers.")
    if len(portfolio)<len(targets):
        raise ValueError(f"Need {len(targets)} assigned lineups to fill all reserved entries.")
    prefix = target.split("-",1)[0] if "-" in target else None
    # Keep every non-roster cell, including the embedded player reference table.
    for number,row_index in enumerate(targets):
        row = list(rows[row_index])
        row.extend([""]*max(0,max(indices)+1-len(row)))
        ids = []
        for idx,slot in zip(indices,slots):
            name = str(portfolio.iloc[number][slot])
            value = str(player_ids.get(name,"")).strip()
            if re.fullmatch(r"[1-9]\d*",value) and prefix:
                value = prefix+"-"+value
            if not re.fullmatch(r"[1-9]\d*-[1-9]\d*",value):
                raise ValueError(f"Missing or invalid FanDuel player ID for {name}.")
            if prefix and value.split("-",1)[0]!=prefix:
                raise ValueError(f"Player {name} belongs to a different FanDuel slate.")
            row[idx]=value; ids.append(value)
        if len(set(ids))!=len(ids):
            raise ValueError("A lineup contains the same player more than once.")
        rows[row_index]=row
    output=io.StringIO(newline="")
    csv.writer(output,lineterminator="\r\n").writerows(rows)
    return output.getvalue().encode("utf-8"), len(targets)


def direct_csv_download_link(data, filename, label="DIRECT FANDUEL UPLOAD DOWNLOAD"):
    """Embed the exact verified bytes without the Streamlit media endpoint."""
    import base64
    from html import escape
    if not isinstance(data, bytes):
        raise ValueError("Download data must be verified CSV bytes")
    header = next(csv.reader(io.StringIO(data.decode("utf-8-sig"))), [])
    columns = {c.strip().casefold() for c in header}
    if not columns.intersection({"entry_id", "entry id", "entryid"}) or not columns.intersection({"contest_id", "contest id", "contestid"}):
        raise ValueError("Cannot offer an analysis report as a FanDuel upload")
    encoded = base64.b64encode(data).decode("ascii")
    return ('<a download="' + escape(filename, quote=True) + '" '
            'href="data:text/csv;charset=utf-8;base64,' + encoded + '" '
            'style="display:block;text-align:center;padding:0.65rem;border:1px solid #ff4b4b;'
            'border-radius:0.5rem;color:inherit;text-decoration:none;font-weight:600;">'
            + escape(label) + '</a>')
