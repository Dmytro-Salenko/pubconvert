"""LibreOffice-based converter for Microsoft Publisher (.pub) files."""

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
    """
    if fmt == "docx":
        return _convert_to_docx(input_path, output_dir, timeout)

    # Direct conversion for PDF and SVG
    _run_soffice(
        extra_args=["--convert-to", fmt],
        input_path=input_path,
        output_dir=output_dir,
        timeout=timeout,
    )

    output_file = output_dir / f"{input_path.stem}.{fmt}"
    if not output_file.exists():
        raise ConversionError(f"Conversion produced no output file")

    return output_file.name


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
        stderr = result.stderr.strip()[:200] if result.stderr else "unknown error"
        raise ConversionError(f"LibreOffice conversion failed: {stderr}")
