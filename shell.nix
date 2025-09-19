let
  pkgs = import <nixpkgs> { };
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    black
    isort
    nodejs
    libffi
    openssl
    libxml2
    libxslt
    enchant2
    gettext
    gcc
  ];
  venvDir = "env";

  shellHook = ''
      export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    source env/bin/activate
  '';
}
