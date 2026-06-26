"""HTTP API for dubbing extension"""
import asyncio
import sys
import uuid
import json
import os
import logging
from pathlib import Path
from threading import Thread
from flask import Flask, request, jsonify

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .pipeline.models import DubbingJob, DubbingConfig, DubbingStatus
from .pipeline.dubbing_pipeline import DubbingPipeline

logger = logging.getLogger(__name__)

app = Flask(__name__)
pipeline = DubbingPipeline()
jobs = {}  # {job_id: DubbingJob}


@app.route('/dubbing', methods=['POST'])
def submit_dubbing_job():
    """
    Submit a new dubbing job.

    Request body:
    {
        "video_path": "/path/to/video.mp4",
        "srt_path": "/path/to/subs.srt",
        "output_path": "/path/to/output.mkv",
        "config": {
            "language": "es",
            "voice": "female",
            "tts_engine": "edge",
            "reduce_vocals": 0.7
        }
    }

    Response: {"job_id": "uuid-here", "status": "pending"}
    """
    try:
        data = request.json
        job_id = str(uuid.uuid4())

        job = DubbingJob(
            job_id=job_id,
            video_path=Path(data['video_path']),
            srt_path=Path(data['srt_path']),
            output_path=Path(data['output_path']),
            config=DubbingConfig(**data.get('config', {})),
        )

        jobs[job_id] = job

        def process_job():
            pipeline.process(job)

        thread = Thread(target=process_job, daemon=False)
        thread.start()

        logger.info(f"Submitted dubbing job {job_id}")
        return jsonify({
            'job_id': job_id,
            'status': job.status.value
        }), 200

    except Exception as e:
        logger.error(f"Failed to submit job: {e}")
        return jsonify({'error': str(e)}), 400


@app.route('/dubbing/<job_id>', methods=['GET'])
def get_dubbing_status(job_id):
    """Get status of a dubbing job"""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify({
        'job_id': job.job_id,
        'status': job.status.value,
        'progress_pct': job.progress_pct,
        'message': job.message,
        'error': job.error,
        'output_path': str(job.output_path) if job.output_path else None,
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with mode and capability information"""
    from .integration_layer import capabilities, current_mode
    return jsonify({
        'status': 'ok',
        'mode': current_mode,
        'capabilities': capabilities.to_dict(),
        'detected_modules': capabilities.detected_modules(),
    }), 200


@app.route('/mode', methods=['GET'])
def mode_info():
    """Return current operating mode and detected capabilities"""
    from .integration_layer import capabilities, current_mode
    return jsonify({
        'operating_mode': current_mode,
        'capabilities': capabilities.to_dict(),
        'detected_modules': capabilities.detected_modules(),
        'any_integration': capabilities.any_integration_available(),
    }), 200


def run_api(host: str = '127.0.0.1', port: int = 5000,
            mode: str = None, skip_validate_madrac_subs: bool = False):
    """Start API server

    Args:
        host: Host to bind to
        port: Port to listen on
        mode: Operating mode ('standalone' or 'integrated'), or None for auto
        skip_validate_madrac_subs: Skip MADRAC module validation
    """
    from .integration_layer import (
        detect_capabilities, determine_mode, set_mode, reload_capabilities,
    )

    # Re-detect capabilities in case env was set after module import
    reload_capabilities()
    from .integration_layer import capabilities

    resolved_mode, skip = determine_mode(
        capabilities,
        cli_mode=mode,
        cli_skip_validate=skip_validate_madrac_subs,
    )

    os.environ['MADRAC_OPERATING_MODE'] = resolved_mode
    os.environ['MADRAC_SKIP_VALIDATION'] = str(skip).lower()
    set_mode(resolved_mode, skip)

    logger.info("Starting API server on %s:%s (mode: %s)", host, port, resolved_mode)
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    run_api()
