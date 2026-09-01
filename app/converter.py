"""LibreOffice-based converter for Microsoft Publisher (.pub) files."""

import shutil
import subprocess
from pathlib import Path


class ConversionError(Exception):
    """Raised when file conversion fails."""
    pass


def convert(input_path: Path, output_dir: Path, fmt: str, timeout: int = 120) -> str:
    """Convert a .pub file to the requested format.

    Args:
        input_path: Path to the .pub file.
        output_dir: Directory to write the output file.
        fmt: Target format — "pdf", "docx", or "svg".
        timeout: Max seconds for LibreOffice process.

    Returns:
        Filename of the converted file (not full path).

    Raises:
        ConversionError: If conversion fails at any step.

    After successful conversion, input file and LibreOffice profile
    are deleted. Only the output file remains in output_dir.
    """
    if fmt == "docx":
        output_name = _convert_to_docx(input_path, output_dir, timeout)
    else:
        # Direct conversion for PDF and SVG
        _run_soffice(
            extra_args=["--convert-to", fmt],
            input_path=input_path,
            output_dir=output_dir,
            timeout=timeout,
        )

        output_file = output_dir / f"{input_path.stem}.{fmt}"
        if not output_file.exists():
            raise ConversionError("Conversion produced no output file")

        output_name = output_file.name

    # Privacy: remove source file and LO profile immediately
    _cleanup_job_artifacts(output_dir, keep_filename=output_name)

    return output_name


def _convert_to_docx(input_path: Path, output_dir: Path, timeout: int) -> str:
    """Two-step conversion: PUB → PDF → DOCX.

    LibreOffice opens .pub files in Draw, which cannot export DOCX.
    So we first create a PDF, then convert PDF → DOCX via Writer.
    """
    # Step 1: PUB → PDF
    _run_soffice(
        extra_args=["--convert-to", "pdf"],
        input_path=input_path,
        output_dir=output_dir,
        timeout=timeout,
    )

    pdf_path = output_dir / f"{input_path.stem}.pdf"
    if not pdf_path.exists():
        raise ConversionError("Failed to create intermediate PDF")

    # Step 2: PDF → DOCX (force Writer to open the PDF)
    _run_soffice(
        extra_args=[
            "--infilter", "writer_pdf_import",
            "--convert-to", "docx",
        ],
        input_path=pdf_path,
        output_dir=output_dir,
        timeout=timeout,
    )

    docx_path = output_dir / f"{input_path.stem}.docx"
    if not docx_path.exists():
        raise ConversionError("Failed to create DOCX from intermediate PDF")

    # Clean up intermediate PDF
    pdf_path.unlink(missing_ok=True)

    return docx_path.name


def _cleanup_job_artifacts(output_dir: Path, keep_filename: str) -> None:
    """Remove everything in output_dir except the final output file.

    Deletes input.pub, lo_profile/, and any other temporary artifacts
    that LibreOffice may have created.
    """
    for entry in output_dir.iterdir():
        if entry.name == keep_filename:
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        except OSError:
            pass


def _run_soffice(
    extra_args: list[str],
    input_path: Path,
    output_dir: Path,
    timeout: int,
) -> None:
    """Run a LibreOffice headless conversion command.

    Each call uses a unique UserInstallation profile inside output_dir
    to avoid lock conflicts when multiple conversions run in parallel.
    """
    profile_dir = output_dir / "lo_profile"
    profile_uri = f"file://{profile_dir}"

    cmd = [
        "soffice",
        "--headless",
        "--norestore",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile_uri}",
        *extra_args,
        "--outdir", str(output_dir),
        str(input_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise ConversionError(
            f"Conversion timed out after {timeout} seconds. "
            "The file may be too complex."
        )
    except FileNotFoundError:
        raise ConversionError(
            "LibreOffice is not installed. "
            "Please run this application inside the Docker container."
        )

    if result.returncode != 0:
        # Do not leak stderr details to the user — may contain paths/metadata
        raise ConversionError("LibreOffice conversion failed.")
