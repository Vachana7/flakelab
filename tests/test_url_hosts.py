"""An address may carry a user name and password in front of the host:

    https://user:password@host/path

The part before the @ is a login, not where the command connects to.
Found in real history on 17 Nov 2026 (pydantic, commit 6b0ba11), where the
host was reported as "pydantic" instead of "pppr.pydantic.dev".
"""

from pipedelta.delta import compare
from pipedelta.powers import extract_powers

HEAD = "on: push\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"


def hosts(run: str) -> set[str]:
    text = HEAD + "      - run: " + run + "\n"
    return {p.name for p in extract_powers(text) if p.kind == "network"}


def test_the_real_pydantic_line_names_the_host_not_the_user():
    run = (
        "uv pip install --default-index "
        "https://pydantic:${PPPR_TOKEN}@pppr.pydantic.dev/simple/ mkdocs-material"
    )
    assert hosts(run) == {"pppr.pydantic.dev"}


def test_user_name_only():
    assert hosts("git clone https://deploy@git.example.org/repo.git") == {"git.example.org"}


def test_plain_password():
    assert hosts("curl https://user:hunter2@files.example.org/x") == {"files.example.org"}


def test_password_from_a_shell_variable_without_braces():
    assert hosts("curl https://bot:$TOKEN@files.example.org/x") == {"files.example.org"}


def test_password_from_a_github_expression():
    run = "'curl https://bot:${{ secrets.TOKEN }}@files.example.org/x'"
    assert hosts(run) == {"files.example.org"}


def test_plain_addresses_are_unchanged():
    assert hosts("curl https://stats.example.org/ping") == {"stats.example.org"}
    assert hosts("curl http://Stats.Example.org:8080/ping") == {"stats.example.org"}


def test_an_at_sign_later_in_the_address_is_not_a_login():
    assert hosts("curl https://api.example.org/users?mail=me@other.example.com") == {
        "api.example.org"
    }
    assert hosts("curl https://api.example.org/@scope/package") == {"api.example.org"}


def test_two_addresses_on_one_line():
    run = "curl https://a.example.org/x && curl https://u:p@b.example.org/y"
    assert hosts(run) == {"a.example.org", "b.example.org"}


def test_adding_a_login_to_the_same_host_is_not_a_new_destination():
    old = HEAD + "      - run: pip install -i https://pkgs.example.org/simple/ tool\n"
    new = HEAD + "      - run: pip install -i https://bot:${TOKEN}@pkgs.example.org/simple/ tool\n"
    assert [f for f in compare(old, new) if f.power.kind == "network"] == []
