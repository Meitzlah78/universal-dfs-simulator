"""Recover saved before-swap entries without recomputing player outcomes."""
import csv
import io


def before_swap_csv(saved,contest_id,slots):
    """Return review-only entry rows from the last retained swap result.

    NBA importers normalize metadata as entry ID, contest ID, name, fee.
    Do not mix contests, infer player names or regenerate missing entries.
    """
    if not isinstance(saved,(tuple,list)) or len(saved)<2 or not isinstance(saved[1],dict):return None
    entries=saved[1].get('original_entries')
    if not isinstance(entries,list) or not entries:return None
    size=len(slots)
    if size not in (8,9):return None
    if any(not isinstance(row,(list,tuple)) or len(row)<4+size or str(row[1])!=str(contest_id) for row in entries):return None
    if len({str(row[0]) for row in entries})!=len(entries):return None
    output=io.StringIO(newline='')
    writer=csv.writer(output,lineterminator='\r\n')
    writer.writerow(['Entry ID','Contest ID','Contest Name','Entry Fee',*slots])
    writer.writerows(row[:4+size] for row in entries)
    return output.getvalue().encode('utf-8')
