"""Template tokens in feed text must not be expanded."""

from build_around_nj_demo import render_template


def test_story_html_tokens_are_not_rescanned():
    html = render_template(
        "start {{PARTNER_ITEMS}} {{COVERAGE_ROWS}} end",
        {
            "{{PARTNER_ITEMS}}": "<li>{{COVERAGE_ROWS}}</li>",
            "{{COVERAGE_ROWS}}": "<tr>real</tr>",
        },
    )
    assert html == "start <li>{{COVERAGE_ROWS}}</li> <tr>real</tr> end"
