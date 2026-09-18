"""Test script to verify Airtable, Mailchimp, and Anthropic API connections."""

import os
import sys
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load environment variables
load_dotenv()


def test_airtable():
    """Test Airtable connection and fetch recent submissions."""
    print("\n" + "=" * 50)
    print("TESTING AIRTABLE CONNECTION")
    print("=" * 50)

    try:
        from pyairtable import Api

        api = Api(os.getenv("AIRTABLE_PAT"))
        table = api.table(os.getenv("AIRTABLE_BASE_ID"), os.getenv("AIRTABLE_TABLE_ID"))

        # Fetch recent records
        records = table.all(max_records=5)
        print("✅ Airtable connected successfully!")
        print(f"   Found {len(records)} recent submissions")

        if records:
            print("\n   Latest submission:")
            latest = records[0]["fields"]
            for key, value in latest.items():
                # Truncate long values
                display_val = str(value)[:60] + "..." if len(str(value)) > 60 else value
                print(f"   - {key}: {display_val}")

        return True
    except Exception as e:
        print(f"❌ Airtable connection failed: {e}")
        return False


def test_mailchimp():
    """Test Mailchimp connection and fetch account info."""
    print("\n" + "=" * 50)
    print("TESTING MAILCHIMP CONNECTION")
    print("=" * 50)

    try:
        import mailchimp_marketing as MailchimpMarketing
        from mailchimp_marketing.api_client import ApiClientError

        client = MailchimpMarketing.Client()
        client.set_config(
            {
                "api_key": os.getenv("MAILCHIMP_API_KEY"),
                "server": os.getenv("MAILCHIMP_SERVER_PREFIX"),
            }
        )

        # Test connection with ping
        response = client.ping.get()
        print(f"✅ Mailchimp connected: {response.get('health_status')}")

        # Get account info
        account = client.root.get_root()
        print(f"   Account: {account.get('account_name')}")
        print(f"   Email: {account.get('email')}")

        # Check template access
        template_id = os.getenv("MAILCHIMP_TEMPLATE_ID")
        if template_id:
            try:
                template = client.templates.get_template(template_id)
                print(f"   Template '{template.get('name')}' accessible ✓")
            except Exception:
                print(f"   ⚠️  Could not access template {template_id}")

        # Check list access
        list_id = os.getenv("MAILCHIMP_LIST_ID")
        if list_id:
            try:
                audience = client.lists.get_list(list_id)
                print(
                    f"   Audience '{audience.get('name')}' has {audience.get('stats', {}).get('member_count', 'N/A')} subscribers"
                )
            except Exception:
                print(f"   ⚠️  Could not access list {list_id}")

        return True
    except ApiClientError as e:
        print(f"❌ Mailchimp connection failed: {e.text}")
        return False
    except Exception as e:
        print(f"❌ Mailchimp connection failed: {e}")
        return False


def test_anthropic():
    """Test Anthropic API connection."""
    print("\n" + "=" * 50)
    print("TESTING ANTHROPIC (CLAUDE) CONNECTION")
    print("=" * 50)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Simple test message
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            messages=[
                {
                    "role": "user",
                    "content": "Say 'API connection successful' and nothing else.",
                }
            ],
        )

        response_text = message.content[0].text
        print("✅ Anthropic connected successfully!")
        print(f"   Model response: {response_text}")
        print(f"   Input tokens: {message.usage.input_tokens}")
        print(f"   Output tokens: {message.usage.output_tokens}")

        return True
    except Exception as e:
        print(f"❌ Anthropic connection failed: {e}")
        return False


def main():
    print("\n" + "#" * 50)
    print("# DNR AUTOMATION - CONNECTION TEST")
    print("#" * 50)

    results = {
        "Airtable": test_airtable(),
        "Mailchimp": test_mailchimp(),
        "Anthropic": test_anthropic(),
    }

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    all_passed = True
    for service, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {service}: {status}")
        if not passed:
            all_passed = False

    print("\n")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
