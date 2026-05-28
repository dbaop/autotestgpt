from flask import jsonify, request

from models import KnowledgeBase, db
from service.document_import_service import parse_uploaded_file
from service.knowledge_service import knowledge_service


def list_knowledge_bases():
    knowledge_bases = knowledge_service.list_knowledge_bases()
    return jsonify({"items": [item.to_dict() for item in knowledge_bases]})


def create_knowledge_base():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Missing required field", "message": "name is required"}), 400

    existing = KnowledgeBase.query.filter_by(name=name).first()
    if existing:
        return jsonify({"error": "Duplicate knowledge base", "message": "Knowledge base already exists"}), 409

    knowledge_base = knowledge_service.create_knowledge_base(name, data.get("description", ""))
    return jsonify({"message": "Knowledge base created", "knowledge_base": knowledge_base.to_dict()}), 201


def get_knowledge_base(knowledge_base_id: int):
    knowledge_base = db.get_or_404(KnowledgeBase, knowledge_base_id)
    result = knowledge_base.to_dict()
    result["entries"] = [entry.to_dict() for entry in knowledge_service.list_entries(knowledge_base_id)]
    return jsonify(result)


def create_knowledge_entry(knowledge_base_id: int):
    db.get_or_404(KnowledgeBase, knowledge_base_id)
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"error": "Missing required fields", "message": "title and content are required"}), 400

    entry = knowledge_service.add_entry(
        knowledge_base_id=knowledge_base_id,
        title=title,
        content=content,
        tags=data.get("tags") or [],
        source_type=data.get("source_type", "manual"),
        source_ref=data.get("source_ref"),
    )
    return jsonify({"message": "Knowledge entry created", "entry": entry.to_dict()}), 201


def import_knowledge_entry(knowledge_base_id: int):
    db.get_or_404(KnowledgeBase, knowledge_base_id)
    upload = request.files.get("file")
    title = (request.form.get("title") or "").strip() or "Imported document"
    tags = [item.strip() for item in (request.form.get("tags") or "").split(",") if item.strip()]

    if not upload or not upload.filename:
        return jsonify({"error": "Missing file", "message": "Please upload a knowledge file"}), 400

    content = parse_uploaded_file(upload.filename, upload.read())
    if not content:
        return jsonify({"error": "Empty file", "message": "Uploaded file does not contain readable content"}), 400

    entry = knowledge_service.import_document_entry(
        knowledge_base_id=knowledge_base_id,
        title=title,
        content=content,
        tags=tags,
        source_ref=upload.filename,
    )
    return jsonify({"message": "Knowledge document imported", "entry": entry.to_dict()}), 201


def search_knowledge_entries():
    data = request.get_json() or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Missing required field", "message": "query is required"}), 400

    items = knowledge_service.search_entries(
        query=query,
        knowledge_base_ids=data.get("knowledge_base_ids") or None,
        limit=int(data.get("limit") or 5),
    )
    return jsonify({"items": items, "total": len(items)})
