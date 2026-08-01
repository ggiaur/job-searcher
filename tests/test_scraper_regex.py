from tools.scraper import JobScraper


def test_parse_markdown_listings_standard_link():
    scraper = JobScraper(mock_mode=True)
    markdown = "[IT vezető](https://www.profession.hu/allas/it-vezeto-123)"
    items = scraper._parse_markdown_listings(markdown, "https://www.profession.hu")
    
    assert len(items) == 1
    assert items[0]["title"] == "IT vezető"
    assert items[0]["url"] == "https://www.profession.hu/allas/it-vezeto-123"

def test_parse_markdown_listings_heading_link():
    scraper = JobScraper(mock_mode=True)
    markdown = "## [IT osztályvezető](https://www.profession.hu/allas/it-osztalyvezeto-456)"
    items = scraper._parse_markdown_listings(markdown, "https://www.profession.hu")
    
    assert len(items) == 1
    assert items[0]["title"] == "IT osztályvezető"
    assert items[0]["url"] == "https://www.profession.hu/allas/it-osztalyvezeto-456"

def test_parse_markdown_listings_filters_navigation_links():
    scraper = JobScraper(mock_mode=True)
    markdown = """
    [Megnézem az állást](https://www.profession.hu/allas/test-1)
    [Részletek](https://www.profession.hu/allas/test-2)
    [Valid IT Manager](https://www.profession.hu/allas/it-manager-789)
    """
    items = scraper._parse_markdown_listings(markdown, "https://www.profession.hu")
    
    assert len(items) == 1
    assert items[0]["title"] == "Valid IT Manager"

def test_parse_markdown_listings_filters_irrelevant_keywords():
    scraper = JobScraper(mock_mode=True)
    markdown = """
    [Éttermi Pultos](https://www.profession.hu/allas/pultos-123)
    [Informatikai Vezető](https://www.profession.hu/allas/it-vezeto-999)
    """
    items = scraper._parse_markdown_listings(markdown, "https://www.profession.hu")
    
    assert len(items) == 1
    assert items[0]["title"] == "Informatikai Vezető"

def test_parse_markdown_listings_only_profession_allas_urls():
    scraper = JobScraper(mock_mode=True)
    markdown = """
    [Kategória Link](https://www.profession.hu/allasok/it)
    [Valid Állás](https://www.profession.hu/allas/valid-job-000)
    """
    items = scraper._parse_markdown_listings(markdown, "https://www.profession.hu")
    
    assert len(items) == 1
    assert items[0]["url"] == "https://www.profession.hu/allas/valid-job-000"
