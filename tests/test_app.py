import unittest

from app import create_app


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_homepage_returns_success(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"News History", response.data)

    def test_search_with_valid_query_returns_success(self):
        response = self.client.post(
            "/api/search",
            json={"query": "  climate change  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["success"], True)
        self.assertEqual(response.json["query"], "climate change")
        self.assertEqual(response.json["results"], [])

    def test_search_with_empty_query_returns_client_error(self):
        response = self.client.post("/api/search", json={"query": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["success"], False)
        self.assertEqual(response.json["error"], "Search query cannot be empty.")

    def test_search_without_json_returns_client_error(self):
        response = self.client.post("/api/search", data="query=climate%20change")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["success"], False)


if __name__ == "__main__":
    unittest.main()
