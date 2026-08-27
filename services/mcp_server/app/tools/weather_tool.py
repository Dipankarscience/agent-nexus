"""
Weather Tool - Fetches current weather using Open-Meteo API (free, no key required).
"""

import logging
import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


async def fetch_weather(city: str) -> str:
    """Fetch current weather for a city using Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Step 1: Geocode the city name to get coordinates
            geo_response = await client.get(
                GEOCODING_URL,
                params={"name": city, "count": 1, "language": "en", "format": "json"},
            )
            geo_response.raise_for_status()
            geo_data = geo_response.json()

            if not geo_data.get("results"):
                return f"Could not find location: '{city}'. Please check the city name and try again."

            location = geo_data["results"][0]
            lat = location["latitude"]
            lon = location["longitude"]
            resolved_name = location.get("name", city)
            country = location.get("country", "")

            # Step 2: Fetch weather data
            weather_response = await client.get(
                WEATHER_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m",
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                },
            )
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            current = weather_data.get("current", {})

            weather_code = current.get("weather_code", 0)
            condition = _weather_code_to_description(weather_code)

            temp = current.get("temperature_2m", "N/A")
            feels_like = current.get("apparent_temperature", "N/A")
            humidity = current.get("relative_humidity_2m", "N/A")
            wind_speed = current.get("wind_speed_10m", "N/A")
            wind_dir = current.get("wind_direction_10m", "N/A")

            return (
                f"🌍 Weather for {resolved_name}, {country}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌡️ Temperature: {temp}°C (Feels like: {feels_like}°C)\n"
                f"☁️ Condition: {condition}\n"
                f"💧 Humidity: {humidity}%\n"
                f"🌬️ Wind: {wind_speed} km/h (Direction: {wind_dir}°)\n"
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching weather: {e}")
        return f"Error fetching weather data: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")
        return f"Error fetching weather data: {str(e)}"


def _weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    weather_codes = {
        0: "Clear sky ☀️",
        1: "Mainly clear 🌤️",
        2: "Partly cloudy ⛅",
        3: "Overcast ☁️",
        45: "Foggy 🌫️",
        48: "Depositing rime fog 🌫️",
        51: "Light drizzle 🌦️",
        53: "Moderate drizzle 🌦️",
        55: "Dense drizzle 🌧️",
        61: "Slight rain 🌧️",
        63: "Moderate rain 🌧️",
        65: "Heavy rain 🌧️",
        71: "Slight snow ❄️",
        73: "Moderate snow 🌨️",
        75: "Heavy snow 🌨️",
        77: "Snow grains 🌨️",
        80: "Slight rain showers 🌦️",
        81: "Moderate rain showers 🌧️",
        82: "Violent rain showers ⛈️",
        85: "Slight snow showers 🌨️",
        86: "Heavy snow showers 🌨️",
        95: "Thunderstorm ⛈️",
        96: "Thunderstorm with slight hail ⛈️",
        99: "Thunderstorm with heavy hail ⛈️",
    }
    return weather_codes.get(code, f"Unknown (code: {code})")


def register_weather_tools(mcp: FastMCP):
    """Register weather tool with FastMCP."""
    @mcp.tool()
    async def get_weather(city: str) -> str:
        """
        Get current weather information for a given city.

        Args:
            city: Name of the city (e.g. 'London', 'Tokyo', 'New York')
        """
        return await fetch_weather(city)
