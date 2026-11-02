{
  description = "Classification des études PDF avec Jev / TypeSafe";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      environment =
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python313.withPackages (ps: [
            ps.pymupdf
            ps.requests
          ]);
          audit = pkgs.writeShellApplication {
            name = "jev-pdf-audit";
            text = ''
              exec ${python}/bin/python ${./jev_pdf_audit.py} "$@"
            '';
          };
        in
        {
          inherit pkgs python audit;
        };
    in
    {
      packages = forAllSystems (
        system:
        let
          env = environment system;
        in
        {
          default = env.audit;
          jev-pdf-audit = env.audit;
        }
      );

      devShells = forAllSystems (
        system:
        let
          env = environment system;
        in
        {
          default = env.pkgs.mkShell {
            packages = [
              env.python
              env.audit
              env.pkgs.uv
            ];
          };
        }
      );

      checks = forAllSystems (
        system:
        let
          env = environment system;
        in
        {
          audit =
            env.pkgs.runCommand "jev-pdf-audit-tests"
              {
                nativeBuildInputs = [
                  env.python
                  env.pkgs.nodejs
                ];
              }
              ''
                cp ${./jev_pdf_audit.py} jev_pdf_audit.py
                cp ${./jev.py} jev.py
                cp ${./viewer.js} viewer.js
                cp -r ${./tests} tests
                export PYTHONDONTWRITEBYTECODE=1
                python -m unittest discover -s tests -v
                node --test tests/viewer.test.cjs
                touch "$out"
              '';
        }
      );
    };
}
