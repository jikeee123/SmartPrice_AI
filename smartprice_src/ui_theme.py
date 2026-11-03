"""Visual system for the five-module management workspace."""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

PALETTE=['#087E8B','#3066BE','#E5A83B','#7C6BB3','#629D87','#D87565']
def apply_theme():
    pio.templates['smartprice']=go.layout.Template(layout=dict(
        font=dict(family='Microsoft YaHei, PingFang SC, sans-serif',color='#263A4D',size=12),
        paper_bgcolor='#FFFFFF',plot_bgcolor='#FFFFFF',colorway=PALETTE,
        margin=dict(l=18,r=18,t=30,b=24),height=340,
        xaxis=dict(showgrid=False,zeroline=False,automargin=True),
        yaxis=dict(gridcolor='#EDF1F5',zeroline=False,automargin=True),
        legend=dict(orientation='h',yanchor='bottom',y=1.02,x=0,title_text=''),
        hoverlabel=dict(bgcolor='#FFFFFF',font_size=13)))
    px.defaults.template='smartprice'; px.defaults.color_discrete_sequence=PALETTE
    st.markdown("""<style>
    :root {--ink:#1C3449;--muted:#64788B;--accent:#087E8B;--line:#E4EBF1;}
    .stApp{background:#F3F6FA;color:var(--ink);font-family:'Microsoft YaHei','PingFang SC',sans-serif;}
    .block-container{max-width:1560px;padding:3.8rem 2.6rem 3rem;}
    h1,h2,h3{letter-spacing:-.025em;color:var(--ink);}
    h3{font-size:1.12rem !important;font-weight:650 !important;}
    [data-testid="stSidebar"]{background:#132D42;border-right:1px solid #203F55;}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"]{color:#DAE6F0;}
    [data-testid="stSidebar"] [role="radiogroup"]{gap:.45rem;}
    [data-testid="stSidebar"] [role="radiogroup"] label{padding:.65rem .8rem;border-radius:8px;color:#D8E4ED;transition:background .15s;}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:#20475D;box-shadow:inset 3px 0 #48BCC0;}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover{background:#1C3D53;}
    [data-testid="stSidebar"] [role="radiogroup"] p{font-size:.91rem;}
    [data-testid="stSidebar"] [role="spinbutton"], [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] button{color:#233C51;}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"]{color:#AFC4D5;}
    [data-testid="stSidebar"] button [data-testid="stMarkdownContainer"]{color:#233C51;}
    .brand{display:flex;gap:12px;align-items:center;margin:8px 0 20px;color:#FFFFFF;}
    .brand svg{flex-shrink:0;}
    .brand strong{display:block;font-size:1.25rem;letter-spacing:-.02em;}
    .brand span{display:block;font-size:.72rem;color:#A9C5D5;margin-top:4px;}
    .module-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:1rem;border-bottom:1px solid var(--line);padding-bottom:1.3rem;}
    .module-header h1{font-size:1.9rem;line-height:1.35;margin:0 0 .45rem;font-weight:750;}
    .module-header p{color:var(--muted);font-size:.9rem;margin:0;line-height:1.7;}
    .environment{white-space:nowrap;color:#08746A;background:#E7F4EF;border:1px solid #CDE7DE;border-radius:5px;padding:6px 10px;font-size:.75rem;margin-top:5px;}
    [data-testid="stMetric"]{background:white;border:1px solid var(--line);border-top:3px solid #087E8B;border-radius:8px;padding:1rem 1.1rem;min-height:110px;}
    [data-testid="stMetricLabel"]{color:var(--muted);font-size:.83rem;}
    [data-testid="stMetricValue"]{font-size:1.65rem;letter-spacing:-.035em;font-weight:650;color:var(--ink);}
    [data-testid="stTabs"] [role="tablist"]{gap:1.3rem;border-bottom:1px solid var(--line);margin-bottom:1rem;}
    [data-testid="stTabs"] [role="tab"]{padding:.7rem .15rem;color:var(--muted);font-size:.9rem;}
    [data-testid="stTabs"] [role="tab"][aria-selected="true"]{color:var(--accent);font-weight:650;}
    [data-testid="stPlotlyChart"]{background:#FFF;border:1px solid var(--line);border-radius:8px;padding:.25rem;}
    [data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:6px;}
    [data-testid="stExpander"]{background:#FFF;border-radius:8px;border-color:var(--line);}
    [data-testid="stButton"] button,[data-testid="stDownloadButton"] button{border-radius:6px;min-height:2.5rem;}
    button:focus-visible,[role="tab"]:focus-visible{outline:2px solid #087E8B !important;outline-offset:3px;}
    [data-testid="stAppDeployButton"]{display:none;}
    @media(max-width:900px){.block-container{padding:3.6rem 1rem 2rem;}.module-header h1{font-size:1.5rem;}.module-header{flex-wrap:wrap;}[data-testid="stMetricValue"]{font-size:1.3rem;}}
    @media(max-width:760px){[data-testid="stHorizontalBlock"]{flex-direction:column;gap:1rem;}[data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{width:100% !important;flex:1 1 100% !important;}}
    @media(prefers-reduced-motion:reduce){*{transition:none !important;}}
    </style>""",unsafe_allow_html=True)

def brand():
    st.sidebar.markdown("""<div class="brand"><svg width="38" height="42" viewBox="0 0 38 42" aria-hidden="true"><circle cx="19" cy="17" r="13" fill="none" stroke="#54C7C1" stroke-width="2"/><circle cx="19" cy="17" r="4" fill="#54C7C1"/><path d="M19 4v26M6 17h26M10 8l18 18M28 8L10 26M19 21L9 40M19 21l10 19M7 40h24" stroke="#A5D9DF" stroke-width="1.5"/></svg><div><strong>SmartPrice AI</strong><span>主题乐园经营决策平台</span></div></div>""",unsafe_allow_html=True)

def module_header(title,description):
    st.markdown(f'<div class="module-header"><div><h1>{title}</h1><p>{description}</p></div><span class="environment">模拟经营环境</span></div>',unsafe_allow_html=True)
