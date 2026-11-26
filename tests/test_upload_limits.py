from types import SimpleNamespace

from upload_limits import validate_uploaded_files


MIB = 1024 * 1024


def uploaded(name: str, size: int):
    return SimpleNamespace(name=name, size=size)


def test_allows_files_within_individual_and_combined_limits():
    files = [uploaded("one.pdf", 2 * MIB), uploaded("two.docx", 3 * MIB)]

    assert validate_uploaded_files(
        files,
        max_files=5,
        max_file_bytes=5 * MIB,
        max_total_bytes=10 * MIB,
    ) is None


def test_rejects_too_many_files():
    files = [uploaded(f"{index}.txt", 1) for index in range(3)]

    error = validate_uploaded_files(
        files,
        max_files=2,
        max_file_bytes=5 * MIB,
        max_total_bytes=10 * MIB,
    )

    assert error == "Upload no more than 2 files at a time."


def test_rejects_a_file_over_the_individual_limit():
    error = validate_uploaded_files(
        [uploaded("large.pdf", 6 * MIB)],
        max_files=5,
        max_file_bytes=5 * MIB,
        max_total_bytes=10 * MIB,
    )

    assert error == "Each file must be 5 MB or smaller."


def test_rejects_combined_uploads_over_the_total_limit():
    files = [uploaded("one.pdf", 6 * MIB), uploaded("two.pdf", 5 * MIB)]

    error = validate_uploaded_files(
        files,
        max_files=5,
        max_file_bytes=10 * MIB,
        max_total_bytes=10 * MIB,
    )

    assert error == "Combined uploads must be 10 MB or smaller."


def test_rejects_empty_files():
    error = validate_uploaded_files(
        [uploaded("empty.pdf", 0)],
        max_files=5,
        max_file_bytes=5 * MIB,
        max_total_bytes=10 * MIB,
    )

    assert error == "Empty files are not accepted."


def test_fails_closed_when_file_size_cannot_be_verified():
    error = validate_uploaded_files(
        [SimpleNamespace(name="unknown.pdf")],
        max_files=5,
        max_file_bytes=5 * MIB,
        max_total_bytes=10 * MIB,
    )

    assert error == "Could not verify an uploaded file size. Please re-upload your files."
