from mcp import MCPServer, Tool, Root
from mcp.transports import HTTPTransport

# 1. Dynamic Company Fetch Tool
class CompanyListTool(Tool):
    """
    Fetches a list of companies near a ZIP code.
    Tries Fortune API first, then falls back to scraping.
    Returns list of {name, location, careers_url}.
    """
    def __init__(self):
        super().__init__(transport=HTTPTransport())
        self.fortune_url = "https://fortune.com/api/v2/list/fortune-500/companies?limit=500"

    def run(self, zip_code: str, radius_miles: int) -> list:
        # Attempt Fortune internal API
        try:
            resp = self.transport.get(self.fortune_url)
            companies = resp.json().get('companies', [])
            # TODO: geocode and filter by distance to zip_code
            return [
                {
                    'name': comp['name'],
                    'location': comp.get('headquarters'),
                    'careers_url': comp.get('careersUrl')
                }
                for comp in companies if comp.get('careersUrl')
            ]
        except Exception:
            # Fallback to basic HTML scrape
            html = self.transport.get("https://fortune.com/fortune500/2024/").text
            # TODO: parse HTML for company names and detail pages
            return []

# 2. Tools for fetching and parsing
class FetchPageTool(Tool):
    """Fetch raw HTML from a given URL"""
    def __init__(self):
        super().__init__(transport=HTTPTransport())
    def run(self, url: str) -> str:
        return self.transport.get(url).text

class ParseJobsTool(Tool):
    """Extracts jobs from HTML via LLM"""
    prompt_template = (
        "You are a scraper. Given this HTML, extract every job posting."
        " Return title, location, link, and required skills as JSON list."
    )
    def run(self, html: str) -> list:
        return self.llm.complete(self.prompt_template, html)

class ParseResumeTool(Tool):
    """Extracts skills from resume text via LLM"""
    prompt_template = (
        "You are a resume analyzer. From this text, extract all relevant skills"
        " (e.g., Python, React, penetration testing) as a JSON list."
    )
    def run(self, resume_text: str) -> list:
        return self.llm.complete(self.prompt_template, resume_text)

class FilterJobsTool(Tool):
    """Filters a list of jobs by candidate skills"""
    def run(self, jobs: list, skills: list) -> list:
        return [job for job in jobs if set(job.get('skills', [])).issubset(skills)]

# 3. Root flow ties everything together
class ITJobCrawler(Root):
    """
    Entry point: returns matching IT jobs for a resume within a ZIP code radius
    """
    def run(self, resume_text: str, zip_code: str, radius_miles: int = 50) -> dict:
        companies = self.invoke(CompanyListTool(), zip_code, radius_miles)
        skills = self.invoke(ParseResumeTool(), resume_text)
        results = {}
        for comp in companies:
            url = comp.get('careers_url')
            html = self.invoke(FetchPageTool(), url)
            jobs = self.invoke(ParseJobsTool(), html)
            matches = self.invoke(FilterJobsTool(), jobs, skills)
            if matches:
                results[comp['name']] = matches
        return results

# 4. Assemble server
server = MCPServer(
    tools=[CompanyListTool, FetchPageTool, ParseJobsTool, ParseResumeTool, FilterJobsTool],
    roots=[ITJobCrawler],
)

if __name__ == '__main__':
    import argparse, json
    parser = argparse.ArgumentParser(description="Test IT Job Crawler")
    parser.add_argument('--resume', required=True, help='Path to resume text file')
    parser.add_argument('--zip', required=True, help='ZIP code for radius search')
    parser.add_argument('--radius', type=int, default=50, help='Radius in miles')
    args = parser.parse_args()

    # Read resume
    with open(args.resume, 'r') as f:
        resume_text = f.read()

    # Directly invoke crawler for test
    crawler = ITJobCrawler()
    output = crawler.run(resume_text, args.zip, args.radius)
    print(json.dumps(output, indent=2))

    # Start server
    print("Starting MCP server on port 8000...")
    server.serve(port=8000)
