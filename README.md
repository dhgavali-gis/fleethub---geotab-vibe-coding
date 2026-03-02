# Fleet Intelligence Hub

A comprehensive Fleet Management System integrating **Geotab Telematics**, **Geotab ACE**, **TomTom Traffic**, **Google Maps Platform (MCP)**, and **Generative AI (Gemini)** to provide real-time monitoring, historical analysis, and intelligent insights.

![Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)
![PydanticAI](https://img.shields.io/badge/AI-PydanticAI-E92063)

## 🚀 Key Features

### 📡 Real-time Monitoring
- **Live 1.0**: Standard real-time vehicle tracking using Geotab API.
- **Live 2.0 (Traffic)**: Enhanced tracking with live traffic flow and incident overlays powered by TomTom API.

### 🕰️ Historical Analysis
- **History 1.0**: Playback vehicle trips and visualize exception events (speeding, harsh cornering, etc.) for any date.
- **History 2.0 (Compare)**: **[Pro Feature]** Advanced visualization to compare "Planned vs. Actual":
  - **Delivery Tracking**: Upload Excel/CSV manifests to see scheduled stops.
  - **Route Comparison**: Upload GeoJSON planned routes to verify driver compliance.

### 📊 Dashboard & Analytics
- **Fleet KPIs**: Aggregated statistics for Safety, Vehicle Health, Fuel Efficiency, and Distance.
- **AI Summary**: One-click generation of professional fleet reports using Gemini, identifying trends and actionable advice.
- **Coaching**: Individual driver scoring and AI-generated coaching tips powered by **Geotab ACE**.

### 🧠 AI Chat (MCP Agent)
- **Natural Language Querying**: Ask complex questions like *"Show me all speeding violations for Demo-18 yesterday"* or *"How is the fleet's fuel efficiency compared to last week?"*.
- **Agentic Capabilities**: The AI can query the local **DuckDB** database, call Geotab APIs, use **Google Maps MCP** for place search & routing, and control the frontend map to visualize results dynamically.

---

## 🛠️ Technical Architecture

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (High-performance Async Python web framework).
- **Database**: [DuckDB](https://duckdb.org/) (In-process SQL OLAP database for fast analytics on fleet data).
- **AI Engine**: [PydanticAI](https://github.com/pydantic/pydantic-ai) + Google Gemini Pro + **Geotab ACE API** + **Google Maps MCP**.
- **Services**: Modular service architecture (`ace_service`, `fleet_service`, `traffic_service`, etc.).

### Frontend
- **Core**: Vanilla JavaScript / HTML5 / CSS3.
- **Mapping**: [Leaflet.js](https://leafletjs.com/).
- **Visualization**: [Chart.js](https://www.chartjs.org/) for analytics.
- **Data Processing**: [SheetJS](https://sheetjs.com/) for client-side Excel parsing.

---

## 📦 Installation & Setup

### Prerequisites
- Python 3.10 or higher.
- A Geotab database account.
- API Keys for Google Gemini, Google Map and TomTom.

### 1. Clone the Repository


### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory with the following credentials:
```ini
# Geotab Credentials
GEOTAB_USERNAME=your_username
GEOTAB_PASSWORD=your_password
GEOTAB_DATABASE=your_database_name
GEOTAB_SERVER=my.geotab.com

# AI & Map Services
GEMINI_API_KEY=your_google_gemini_key
TOMTOM_API_KEY=your_tomtom_api_key
```

### 4. Run the Application
```bash
uvicorn main:app --reload
```
Access the application at: `http://localhost:8000`

---

## 📂 Project Structure

### 🚗 Demo Data
This project utilizes the **"Long Distance with Tachograph"** demo dataset provided by **Geotab**, which simulates realistic fleet operations including long-haul trucking scenarios, tachograph compliance data, and diverse exception events.

```
demo_project_v2/
├── PydanticAI/             # AI Agent logic and tools
│   ├── agent.py            # Main Agent definition
│   └── tools.py            # Tools available to the AI (SQL, API calls)
├── services/               # Business logic modules
│   ├── ai_summary_service.py # Fleet report generation
│   ├── mcp_service.py      # Chat interface handler
│   ├── traffic_service.py  # TomTom integration
│   └── ...
├── static/                 # Frontend assets
│   ├── index.html          # Main Single Page Application
│   └── ...
├── documents/              # Project documentation
├── main.py                 # FastAPI entry point
└── requirements.txt        # Python dependencies
```

## 📝 API Documentation
Once the server is running, full API documentation (Swagger UI) is available at:
`http://localhost:8000/docs`

## Architecture Diagram

<img width="7255" height="4057" alt="Project Idea to Deployment-2026-03-02-230424" src="https://github.com/user-attachments/assets/e51e36c3-95df-4da8-b6c5-6d3f38c92a1c" />

##Output

#1. Agentic Chatbot - Google Gemini + GMP MCP + Geotab Ace 
<img width="1468" height="838" alt="Screenshot 2026-03-03 at 4 39 35 AM" src="https://github.com/user-attachments/assets/3fcfa3d9-9d59-4a23-8c3b-f8560c8f2e4c" />

#2. Dashboard with AI summary & Insights
<img width="1470" height="835" alt="Screenshot 2026-03-03 at 4 40 48 AM" src="https://github.com/user-attachments/assets/90557755-bf5d-4cee-953f-da8fe802f99a" />
<img width="1469" height="836" alt="Screenshot 2026-03-03 at 4 43 00 AM" src="https://github.com/user-attachments/assets/3072a09a-9673-4cb6-b457-57aa16d8a64a" />


#3. Historical Tracking: Addons - Planned route rendering + delivery locations 
<img width="1466" height="773" alt="Screenshot 2026-03-03 at 4 45 43 AM" src="https://github.com/user-attachments/assets/e585af40-18b0-466b-bf00-6f3edcfd013c" />

<img width="1468" height="837" alt="Screenshot 2026-03-03 at 4 46 01 AM" src="https://github.com/user-attachments/assets/891063dd-df3c-4eae-bf27-4bcc13c3acd7" />




## 🛡️ License
Proprietary / Demo Use Only.





