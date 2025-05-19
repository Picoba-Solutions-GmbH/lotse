import io
import ssl
import urllib.request

import pandas as pd
import plotly.express as px
import urllib3

from dash import Dash, Input, Output, callback, dcc, html

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create unverified SSL context
ssl_context = ssl._create_unverified_context()

# URL of the file
url = "https://raw.githubusercontent.com/plotly/datasets/master/gapminder_unfiltered.csv"

# Download the file with the custom SSL context
with urllib.request.urlopen(url, context=ssl_context) as response:
    csv_content = response.read().decode('utf-8')

# Convert the CSV content to a pandas DataFrame
df = pd.read_csv(io.StringIO(csv_content))

app = Dash(__name__)

# Fix the layout to be a proper component
app.layout = html.Div([
    html.H1(children='Title of Dash App', style={'textAlign': 'center'}),
    dcc.Dropdown(df.country.unique(), 'Canada', id='dropdown-selection'),
    dcc.Graph(id='graph-content')
])


@callback(
    Output('graph-content', 'figure'),
    Input('dropdown-selection', 'value')
)
def update_graph(value):
    dff = df[df.country == value]
    return px.line(dff, x='year', y='pop')


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")
