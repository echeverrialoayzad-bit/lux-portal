#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lux Portal - Entry Point
Portal modular para herramientas FreightWise
"""

import os
from lux_portal import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    use_https = os.environ.get('USE_HTTPS', 'true').lower() == 'true'

    if use_https:
        print("\n" + "="*60)
        print("  Lux Portal - Servidor HTTPS")
        print("="*60)
        print(f"  URL: https://localhost:{port}")
        print("  Usuario: admin")
        print("  Contrasena: freightwise2025")
        print("="*60)
        print("  NOTA: El navegador mostrara advertencia de certificado")
        print("  Haz clic en 'Avanzado' y luego 'Continuar'")
        print("="*60 + "\n")
        app.run(host='0.0.0.0', port=port, debug=True, ssl_context='adhoc')
    else:
        print(f"\n  Lux Portal: http://localhost:{port}\n")
        app.run(host='0.0.0.0', port=port, debug=True)
