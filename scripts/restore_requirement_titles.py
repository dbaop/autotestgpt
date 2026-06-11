"""One-time repair: restore requirement titles that were overwritten by the
requirement-parsing step with the LLM/page-derived title.

The original user-entered title was captured at creation time in the auto-created
conversation's title as "需求 #<id> · <original title>" (truncated to 40 chars).
We recover it from there. Read-only by default; pass --apply to write.

Usage:
    python scripts/restore_requirement_titles.py          # dry run
    python scripts/restore_requirement_titles.py --apply  # apply changes
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import main  # noqa: E402  builds Flask app + db
from models import Conversation, Requirement, db  # noqa: E402

_PREFIX_RE = re.compile(r"^需求\s*#\d+\s*·\s*")


def _original_title_from_conv(conv_title: str) -> str:
    if not conv_title:
        return ""
    return _PREFIX_RE.sub("", conv_title).strip()


def main_run(apply: bool) -> None:
    with main.app.app_context():
        changes = []
        for req in Requirement.query.order_by(Requirement.id).all():
            conv = (
                Conversation.query.filter_by(requirement_id=req.id)
                .order_by(Conversation.id.asc())
                .first()
            )
            if not conv:
                continue
            original = _original_title_from_conv(conv.title or "")
            if not original:
                continue
            current = (req.title or "").strip()
            # Only restore when the current title differs from the captured original
            # (the overwrite case). Equal titles were never clobbered.
            if original and original != current:
                changes.append((req.id, current, original))

        if not changes:
            print("No titles need restoring.")
            return

        print(f"{'APPLY' if apply else 'DRY RUN'} — {len(changes)} requirement(s):")
        for rid, cur, orig in changes:
            print(f"  req {rid}: {cur!r}  ->  {orig!r}")

        if apply:
            for rid, _cur, orig in changes:
                req = db.session.get(Requirement, rid)
                if req:
                    req.title = orig
            db.session.commit()
            print(f"Applied {len(changes)} title restore(s).")
        else:
            print("\nRe-run with --apply to write these changes.")


if __name__ == "__main__":
    main_run(apply="--apply" in sys.argv)
