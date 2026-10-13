package fr.scanmylib.api

/** Example payloads of docs/API.md, with concrete values. */
object ApiFixtures {
    const val DOCUMENT_ID = "6f1c2d3e-4b5a-4c6d-8e7f-90a1b2c3d4e5"
    const val PAGE_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

    const val HEALTH = """{"name": "ScanMyLib", "version": "0.1.0", "api": 1}"""

    const val STATUS = """
        {
          "version": "0.1.0",
          "ocr": {"reachable": true, "state": "idle", "backend": "vllm", "last_error": null,
                  "gpu": {"name": "NVIDIA GeForce RTX 3090", "memory_used_mb": 5120, "memory_total_mb": 24576}},
          "queue": {"queued": 3, "processing": 1, "error": 0, "done": 120},
          "library_dir": "/home/user/Documents/ScanMyLib"
        }
    """

    const val DOCUMENT = """
        {
          "id": "$DOCUMENT_ID",
          "slug": "example-book",
          "title": "Example Book",
          "author": "Jane Doe",
          "kind": "book",
          "notes": "",
          "unwarp": false,
          "created_at": "2026-10-12T19:00:00+02:00",
          "updated_at": "2026-10-12T20:00:00+02:00",
          "stats": {"pages": 42, "done": 40, "queued": 1, "processing": 1, "error": 0, "excluded": 0, "duplicates": 0},
          "coverage": {"ranges": [[1, 12], [45, 60]], "label": "1–12, 45–60", "gaps": [[13, 44]],
                       "min": 1, "max": 60, "unnumbered": 3},
          "cover_thumb_url": "/api/pages/$PAGE_ID/thumb",
          "folder": "/home/user/Documents/ScanMyLib/example-book"
        }
    """

    const val PAGE = """
        {
          "id": "$PAGE_ID",
          "document_id": "$DOCUMENT_ID",
          "key": "20261012-201530_1a2b3c4d",
          "session_id": "0b1c2d3e-0000-4000-8000-000000000001", "seq": 3,
          "captured_at": "2026-10-12T20:15:30+02:00", "uploaded_at": "2026-10-12T20:16:00+02:00",
          "status": "done",
          "error": null,
          "number": 42,
          "number_end": null,
          "page_label": "42",
          "number_source": "detected",
          "detected_numbers": ["42"],
          "hint_number": null,
          "manual_number": null,
          "excluded": false,
          "duplicate_of": null,
          "in_document": true,
          "rotation": 0,
          "width": 2480, "height": 3508,
          "ocr": {"engine": "paddleocr-vl-1.6", "duration_s": 2.3, "at": "2026-10-12T20:16:05+02:00", "images": 2, "chars": 2345},
          "thumb_url": "/api/pages/$PAGE_ID/thumb",
          "image_url": "/api/pages/$PAGE_ID/image"
        }
    """

    /** `GET /api/documents/{id}`: the document and its pages. */
    val DOCUMENT_DETAIL = DOCUMENT.trimEnd().removeSuffix("}") + """, "pages": [$PAGE]}"""
}
