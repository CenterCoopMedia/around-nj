"""The network feed must not bring out-of-state headlines into Around NJ."""

from build_around_nj_demo import filter_tapinto_network_items, tapinto_town_sources


def test_network_feed_keeps_listed_nj_towns_with_town_credit():
    config = {
        "feeds": {
            "hyperlocal_essex": [
                {
                    "name": "TAPinto Bloomfield",
                    "rss_url": "https://www.tapinto.net/towns/bloomfield/rss",
                }
            ]
        }
    }
    directory = {
        "subscription_towns": [
            {
                "name": "Raritan Bay",
                "slug": "raritan-bay",
                "state": "NJ",
                "cluster_towns": [
                    {"name": "Woodbridge", "slug": "woodbridge", "state": "NJ"}
                ],
            },
            {"name": "Parkland", "slug": "parkland", "state": "FL"},
        ]
    }
    items = [
        {
            "title": "Raritan Bay news",
            "url": "https://www.tapinto.net/towns/raritan-bay/sections/news/articles/raritan-bay-news",
            "source": "TAPinto (network)",
        },
        {
            "title": "Woodbridge news",
            "url": "https://www.tapinto.net/towns/woodbridge/sections/news/articles/woodbridge-news",
            "source": "TAPinto (network)",
        },
        {
            "title": "Florida news",
            "url": "https://www.tapinto.net/towns/parkland/sections/news/articles/florida-news",
            "source": "TAPinto (network)",
        },
        {
            "title": "Bloomfield Honors Beautification Winners",
            "url": "https://www.tapinto.net/towns/bloomfield/sections/government/articles/bloomfield-honors-beautification-winners",
            "source": "TAPinto (network)",
        },
        {
            "title": "Vermont arts event",
            "url": "https://www.tapinto.net/towns/nyvt-media/sections/arts/articles/vermont-arts-event",
            "source": "TAPinto (network)",
        },
        {
            "title": "Unrelated host",
            "url": "https://example.com/towns/bloomfield/articles/unrelated",
            "source": "TAPinto (network)",
        },
    ]

    assert filter_tapinto_network_items(
        items, tapinto_town_sources(config, directory)
    ) == [
        {**items[0], "source": "TAPinto Raritan Bay"},
        {**items[1], "source": "TAPinto Woodbridge"},
        {**items[3], "source": "TAPinto Bloomfield"},
    ]
