"""python -m metafield_nbody entry."""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "golden":
        from . import golden as GD
        from . import duck
        import os
        os.makedirs(GD.GOLDEN_DIR, exist_ok=True)
        written = GD.write_all()
        for g, path in written:
            if g["kind"] == "ticks":
                g["duck_horizon_ticks"] = duck.calibrate_horizon(g)
            else:
                g["duck_horizon_ticks"] = None
            GD.save(g, path)
            print("wrote", path, "horizon", g.get("duck_horizon_ticks"))
        print("done", len(written), "goldens")
        return 0
    from .cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
