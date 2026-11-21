"""Start printO. This only wires the pieces and runs them."""

from printo.config import load_settings
from printo.runtime import boot, report
from printo.serve import serve


def main(argv: list[str] | None = None) -> None:
    settings = load_settings(argv)
    ctx = boot(settings)
    if settings.check_only:
        try:
            report(ctx)
        finally:
            ctx.db.close()
        return
    serve(ctx)


if __name__ == "__main__":
    main()
