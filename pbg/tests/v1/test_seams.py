from pysed2translate_pbg import host


def test_every_seam_name_exists_in_the_host():
    assert host.check_seams() == []
