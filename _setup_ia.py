
import shutil
import pathlib
import sys

try:
    import prophet
    import cmdstanpy

    prophet_dir = pathlib.Path(prophet.__file__).parent / "stan_model"
    bundled = next(prophet_dir.glob("cmdstan-*"), None)

    if bundled and not (bundled / "makefile").exists():
        fixed = False

        # Tenta copiar o makefile do cmdstan ja instalado no sistema
        try:
            sys_cmdstan = pathlib.Path(cmdstanpy.cmdstan_path())
            src = sys_cmdstan / "makefile"
            if src.exists():
                shutil.copy(src, bundled / "makefile")
                print("  [IA] makefile corrigido usando cmdstan do sistema.")
                fixed = True
        except Exception:
            pass

        if not fixed:
            # Ultimo recurso: baixa e instala o cmdstan (~5 min, so na primeira vez)
            print("  [IA] Instalando CmdStan (aguarde, so ocorre na primeira vez)...")
            cmdstanpy.install_cmdstan()
            print("  [IA] CmdStan instalado.")
    else:
        print("  [IA] Prophet OK.")

except ImportError as e:
    print(f"  [AVISO] Prophet nao encontrado: {e}")
    print("  Execute: pip install prophet")
    sys.exit(0)  # nao bloqueia o servidor, so avisa
