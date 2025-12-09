"""
Click and Typer CLI patterns.
These libraries map env vars to CLI arguments via 'envvar' parameters.
"""
import click
import typer

app = typer.Typer()

# Case 1: Click Option
@click.command()
@click.option('--host', envvar='API_HOST', default='localhost')
@click.option('--port', envvar='API_PORT', type=int)
@click.option('--debug/--no-debug', envvar='DEBUG_MODE')
def serve(host, port, debug):
    pass

# Case 2: Click List (Multiple Env Vars)
@click.command()
@click.option('--db', envvar=['DATABASE_URL', 'DB_URL'])
def connect(db):
    pass

# Case 3: Typer Option
@app.command()
def main(
    api_key: str = typer.Option(..., envvar="API_KEY"),
    timeout: int = typer.Option(30, envvar="REQUEST_TIMEOUT"),
):
    pass

# Case 4: Click Group
@click.group()
@click.option('--config', envvar='APP_CONFIG')
def cli(config):
    pass

@cli.command()
@click.option('--verbose', envvar='VERBOSE')
def run(verbose):
    pass