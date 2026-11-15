"""Cold prospecting bot for Ese Auto (docs/PROSPECCION.md).

Every morning it picks about 30 dealers and resellers (3 to 60 active
listings), builds a JSON of verifiable facts about each one from the database,
has `claude -p` write two WhatsApp messages per prospect and a second
`claude -p` check them against those facts. Juan reads, edits and sends them by
hand from /admin/prospeccion: nothing here sends a message.
"""
