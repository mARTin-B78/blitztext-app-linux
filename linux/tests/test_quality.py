from blitztext.quality import too_quiet, is_hallucination, clean

def test_too_quiet():
    # Below duration
    assert too_quiet(0.5, 1000.0, min_seconds=1.0, silence_rms=500.0) == True
    # Below rms
    assert too_quiet(2.0, 300.0, min_seconds=1.0, silence_rms=500.0) == True
    # Good quality
    assert too_quiet(2.0, 1000.0, min_seconds=1.0, silence_rms=500.0) == False

def test_is_hallucination():
    # Hallucination for short duration
    assert is_hallucination("Thank you.", 2.0) == True
    assert is_hallucination("Vielen Dank", 1.5) == True
    
    # Same phrase but longer duration -> Not considered a hallucination
    assert is_hallucination("Thank you.", 3.0) == False
    
    # Non-hallucination
    assert is_hallucination("This is a valid sentence.", 1.0) == False
    
    # Empty string
    assert is_hallucination("", 1.0) == True
    assert is_hallucination("   ", 1.0) == True

def test_clean():
    assert clean("  hello world  ") == "hello world"
    assert clean("hello world. ", strip_trailing_punctuation=True) == "hello world"
    assert clean("hello world!", strip_trailing_punctuation=True) == "hello world"
    assert clean("hello world", strip_trailing_punctuation=True) == "hello world"
