"""Celery task: full PDF processing pipeline."""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.job import ProcessingJob, JobStatus
from app.services.progress import publish_progress
from app.services.storage import save_md, save_raw_md
from app.workers.pipeline import detector, extractor, images as img_pipeline
from app.workers.pipeline import llm_refine, markdown_builder, tokens
from app.workers.pipeline.ocr import run_ocr, OCRError


def _get_job(db: Session, job_id: str) -> ProcessingJob:
    job = db.get(ProcessingJob, uuid.UUID(job_id))
    if not job:
        raise ValueError(f"Job {job_id} não encontrado")
    return job


def _update_status(db: Session, job: ProcessingJob, status: JobStatus, **kwargs) -> None:
    job.status = status
    for k, v in kwargs.items():
        setattr(job, k, v)
    db.commit()
    publish_progress(str(job.id), {"status": status.value, **kwargs})


@celery_app.task(bind=True, max_retries=0)
def process_pdf(self, job_id: str) -> None:
    db = SyncSessionLocal()
    try:
        job = _get_job(db, job_id)
        pdf_path = job.original_storage_path

        # ── Step 1: OCR detection ──────────────────────────────────────────
        _update_status(db, job, JobStatus.ocr, message="Detectando camada de texto...")

        pages_data = detector.detect_pages(pdf_path)
        total_pages = len(pages_data)
        job.pages_total = total_pages
        db.commit()

        publish_progress(job_id, {
            "status": "ocr",
            "message": f"Analisando {total_pages} páginas...",
            "total": total_pages,
        })

        scanned_count = sum(1 for _, has_text in pages_data if not has_text)

        if scanned_count > 0:
            publish_progress(job_id, {
                "status": "ocr",
                "message": f"Executando OCR em {scanned_count} páginas escaneadas...",
                "total": total_pages,
                "scanned": scanned_count,
            })

            def ocr_progress(page_idx):
                publish_progress(job_id, {
                    "status": "ocr",
                    "message": f"OCR: página {page_idx + 1} concluída",
                    "page": page_idx + 1,
                    "total": total_pages,
                })

            ocr_results = run_ocr(pdf_path, pages_data, progress_callback=ocr_progress)
        else:
            ocr_results = [(i, None) for i, _ in pages_data]

        pages_ocr = sum(1 for _, text in ocr_results if text is not None)
        job.pages_ocr = pages_ocr
        db.commit()

        # ── Step 2: Content extraction ────────────────────────────────────
        _update_status(db, job, JobStatus.extracting, message="Extraindo conteúdo...")

        blocks, raw_blocks = extractor.extract(pdf_path, ocr_results)

        publish_progress(job_id, {
            "status": "extracting",
            "message": "Extraindo imagens...",
        })

        image_texts, docs_found, docs_extracted = img_pipeline.extract_images(pdf_path)
        # Count uses pdfplumber detection directly — independent of OCR success
        pages_with_images = img_pipeline.count_pages_with_images(pdf_path)
        job.pages_with_images = pages_with_images
        db.commit()

        # ── Step 3: Build Markdown ────────────────────────────────────────
        publish_progress(job_id, {
            "status": "extracting",
            "message": "Gerando Markdown...",
        })

        md_content = markdown_builder.build(blocks, image_texts)

        # ── Step 3b: LLM refinement (optional) ───────────────────────────
        llm_tokens_used = None
        raw_path = None
        tokens_raw_output = None
        if job.use_llm:
            # Count tokens of local (pre-LLM) markdown
            tokens_raw_output = tokens.count(md_content)
            # Save raw (pre-LLM) markdown before refinement
            raw_path = save_raw_md(job_id, md_content)
            publish_progress(job_id, {
                "status": "llm_refining",
                "message": "Refinando com IA (GPT-4.1-mini)...",
            })
            result = llm_refine.refine(md_content)
            md_content = result.markdown
            llm_tokens_used = result.tokens_used

        # ── Step 4: Token counting ────────────────────────────────────────
        # Baseline = what the user would send to the LLM *without* our tool:
        #   - full text layer via pdfplumber extract_text() (includes boilerplate)
        #   - plus OCR text for scanned pages (user would also need to OCR those)
        # This makes the reduction metric show the true benefit of boilerplate removal.
        raw_text_layer = tokens.extract_raw_text(pdf_path)
        ocr_text = " ".join(text for _, text in ocr_results if text is not None)
        raw_text = (raw_text_layer + "\n" + ocr_text).strip() if ocr_text else raw_text_layer
        tokens_orig = tokens.count(raw_text) if raw_text.strip() else 1
        tokens_out = tokens.count(md_content)
        reduction_pct = round((1 - tokens_out / tokens_orig) * 100, 2) if tokens_orig > 0 else 0.0
        # Clamp to NUMERIC(7,2) safe range; extreme values occur on near-empty PDFs
        reduction_pct = max(-9999.99, min(9999.99, reduction_pct))

        # ── Step 5: Save output ───────────────────────────────────────────
        output_path = save_md(job_id, md_content)

        # ── Step 6: Finalize ──────────────────────────────────────────────
        import os
        job.status = JobStatus.done
        job.output_storage_path = output_path
        job.tokens_original = tokens_orig
        job.tokens_output = tokens_out
        job.reduction_pct = reduction_pct
        job.original_file_size = os.path.getsize(pdf_path)
        job.output_file_size = os.path.getsize(output_path)
        job.llm_tokens_used = llm_tokens_used
        job.tokens_raw_output = tokens_raw_output
        job.raw_output_path = raw_path
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        publish_progress(job_id, {
            "status": "done",
            "message": "Processamento concluído!",
            "tokens_original": tokens_orig,
            "tokens_output": tokens_out,
            "reduction_pct": float(reduction_pct),
            "original_file_size": job.original_file_size,
            "output_file_size": job.output_file_size,
            "pages_total": total_pages,
            "pages_ocr": pages_ocr,
            "pages_with_images": pages_with_images,
            "docs_found": docs_found,
            "docs_extracted": docs_extracted,
            "llm_tokens_used": llm_tokens_used,
            "tokens_raw_output": tokens_raw_output,
            "has_raw_md": raw_path is not None,
        })

    except OCRError as e:
        _handle_error(db, job_id, str(e))
    except Exception as e:
        _handle_error(db, job_id, f"Erro interno: {e}")
    finally:
        db.close()


def _handle_error(db: Session, job_id: str, message: str) -> None:
    try:
        job = db.get(ProcessingJob, uuid.UUID(job_id))
        if job:
            job.status = JobStatus.error
            job.error_message = message
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        pass
    publish_progress(job_id, {"status": "error", "message": message})
