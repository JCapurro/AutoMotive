from .base import BaseScraper, Listing
from .mercadolibre import MercadoLibreScraper
from .facebook import FacebookMarketplaceScraper
from .v6 import V6Scraper
from .kavak import KavakScraper

REGISTRY = {
    "mercadolibre": MercadoLibreScraper,
    "facebook":     FacebookMarketplaceScraper,
    "v6":           V6Scraper,
    "kavak":        KavakScraper,
}

__all__ = ["BaseScraper", "Listing", "REGISTRY"]
