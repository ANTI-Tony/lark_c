"""IM end-to-end test cases (M2 deliverable).

These tests are intentionally non-destructive: none of them press Send.
Run with::

    python -m cua_lark.cli test tests/feishu/im/

Pre-conditions:
- Feishu desktop is logged in and has at least one conversation in the IM list.
- For CDP-backed assertions, Feishu must be launched with
  ``--remote-debugging-port=9222``. Without that, the runner downgrades
  CDP assertions to a clear failure rather than masking them.
"""

from cua_lark.dsl import cua_test


@cua_test("IM · type a message in the first chat without sending", "im")
def test_im_type_message(ctx) -> None:
    ctx.do("Bring the Feishu (Lark) desktop application to the foreground. "
           "If it isn't running, stop and report that.")
    ctx.do("In Feishu, click the Messages / IM tab in the left sidebar.")
    ctx.do("Open the first conversation in the chat list by clicking it.")
    ctx.do("Click the message input box at the bottom of the chat panel.")
    ctx.do("Type the text 'hello from CUA-Lark' into the input box. "
           "Do NOT press Enter or click Send.")
    ctx.assert_visible(
        "the text 'hello from CUA-Lark' is visible inside the message input box "
        "at the bottom of the chat, and it has not yet been sent"
    )


@cua_test("IM · search for chats by keyword", "im")
def test_im_search_chat(ctx) -> None:
    ctx.do("Bring the Feishu desktop application to the foreground.")
    ctx.do("Click the global search bar at the top of the Feishu window. "
           "Use the keyboard shortcut Cmd+K (macOS) if a direct click is ambiguous.")
    ctx.do("Type the keyword '测试' into the search input.")
    ctx.assert_visible(
        "a search results panel is visible, listing entries whose names or "
        "previews contain the substring '测试'"
    )


@cua_test("IM · open the emoji picker for the first chat", "im")
def test_im_emoji_picker(ctx) -> None:
    ctx.do("Bring the Feishu desktop application to the foreground.")
    ctx.do("Click the Messages / IM tab in the left sidebar.")
    ctx.do("Open the first conversation in the chat list.")
    ctx.do("Click the emoji / smiley icon in the toolbar above the message input box.")
    ctx.assert_visible(
        "an emoji picker panel is now displayed, showing a grid of emoji "
        "characters and (optionally) category tabs"
    )
