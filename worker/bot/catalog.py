"""Catálogo mínimo de opciones para los teclados inline.
Se mantiene chico a propósito: el usuario también puede tipear texto libre."""

MARCAS_POPULARES = [
    "Volkswagen", "Toyota", "Ford", "Chevrolet", "Renault",
    "Fiat", "Peugeot", "Citroen", "Honda", "Nissan",
    "Hyundai", "Kia", "Jeep", "Audi", "BMW",
    "Mercedes-Benz", "Mini", "Subaru", "Mitsubishi", "Suzuki",
]

COMBUSTIBLES = ["Nafta", "Diésel", "GNC", "Híbrido", "Eléctrico"]
TRANSMISIONES = ["Manual", "Automática"]
VENDEDORES = ["particular", "concesionaria"]
MONEDAS = ["USD", "ARS"]

# Year pills for the wizard's multi-select. Range covers most realistic
# searches; outside this range users can use anio_min/anio_max instead.
ANIOS = list(range(2026, 2009, -1))   # 2026, 2025, …, 2010

# All available filter keys + a friendly label and order for the wizard.
# Step types are encoded in the keyboard builder, not here.
WIZARD_STEPS = [
    ("marcas",      "Marcas (podés elegir varias)"),
    ("modelos",     "Modelos (separados por coma)"),
    ("version",     "Versión (opcional)"),
    ("anios",       "Años (podés elegir varios)"),
    ("km_min",      "KM mínimo"),
    ("km_max",      "KM máximo"),
    ("moneda",      "Moneda"),
    ("combustible", "Combustible"),
    ("transmision", "Transmisión"),
    ("vendedor",    "Vendedor"),
    ("user_location", "Tu ubicacion"),
    ("radio_km",    "Rango de busqueda en km"),
    ("sources",     "Plataformas a monitorear"),
]
