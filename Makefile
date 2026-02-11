.PHONY: install uninstall test clean

install:
    @sh install.sh

uninstall:
    @sh uninstall.sh

test:
    @sh tests/test-phase1.sh

clean:
    @echo "Nettoyage..."
    @rm -rf build/ *.pyc

help:
    @echo "YARP Build System"
    @echo ""
    @echo "Cibles disponibles:"
    @echo "  make install    - Installer YARP"
    @echo "  make uninstall  - Désinstaller YARP"
    @echo "  make test       - Lancer les tests"
    @echo "  make clean      - Nettoyer"
