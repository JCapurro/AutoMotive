from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail
from .mercadolibre import MercadoLibreScraper
from .facebook import FacebookMarketplaceScraper
from .v6 import V6Scraper
from .kavak import KavakScraper
from .autocosmos import AutoCosmosScraper

REGISTRY = {
    "mercadolibre": MercadoLibreScraper,
    "facebook":     FacebookMarketplaceScraper,
    "v6":           V6Scraper,
    "kavak":        KavakScraper,
    "autocosmos":   AutoCosmosScraper,
}

__all__ = ["BaseScraper", "CollectorBlocked", "Listing", "ListingDetail", "REGISTRY"]
