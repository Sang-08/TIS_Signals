/* ===================================================================
   CrypT Trading Intelligence — app.js (Steps 0-5 Complete)
   TradingView Lightweight Charts v4 + WebSocket + Markets + Drawer
   =================================================================== */
'use strict';

/* ====================================================================
   §0  UTILITIES
   ==================================================================== */
function fmt(n,d=2){return n!=null?Number(n).toFixed(d):'—';}
function fmtPct(n,d=2){if(n==null)return'—';const s=Number(n).toFixed(d);return(n>=0?'+':'')+s+'%';}
function fmtUSD(n){if(n==null)return'—';const a=Math.abs(n);if(a>=1e9)return'$'+(n/1e9).toFixed(2)+'B';if(a>=1e6)return'$'+(n/1e6).toFixed(2)+'M';if(a>=1e3)return'$'+(n/1e3).toFixed(1)+'K';return'$'+fmt(n);}
function fmtPrice(n,prec){if(n==null)return'—';if(prec!=null)return'$'+Number(n).toFixed(prec);if(n>=1000)return'$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});if(n>=1)return'$'+fmt(n,2);return'$'+fmt(n,4);}
function fmtVol(n){if(n==null)return'—';if(n>=1e9)return(n/1e9).toFixed(2)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(0)+'K';return fmt(n,0);}
function cls(n){return n==null?'neutral':n>=0?'up':'down';}
function clsBg(n){return n==null?'':n>=0?'up-bg':'down-bg';}
function gainLoss(n){return n==null?'':n>=0?'gain':'loss';}
function normPct(v){if(v==null)return null;return v<=1?v*100:v;}
function fmtFunding(v,d=4){if(v==null)return'—';const p=v*100;return(p>=0?'+':'')+p.toFixed(d)+'%';}
function flashPrice(el,ot,nt){if(!el||ot===nt)return;el.textContent=nt;const o=parseFloat(ot.replace(/[^0-9.-]/g,'')),n=parseFloat(nt.replace(/[^0-9.-]/g,''));if(isNaN(o)||isNaN(n)||o===n)return;el.classList.remove('flash-up','flash-down');void el.offsetWidth;el.classList.add(n>o?'flash-up':'flash-down');setTimeout(()=>el.classList.remove('flash-up','flash-down'),700);}
function escHtml(s){if(typeof s!=='string')return'';return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function safeHref(u){if(typeof u!=='string')return'#';return/^https?:\/\//i.test(u)?u:'#';}
function ago(ts){if(!ts)return'';const d=(Date.now()/1000)-ts;if(d<60)return'just now';if(d<3600)return Math.floor(d/60)+'m ago';if(d<86400)return Math.floor(d/3600)+'h ago';return Math.floor(d/86400)+'d ago';}
function agoLong(ts){if(!ts)return'';const d=(Date.now()/1000)-ts;const h=Math.floor(d/3600);if(h<1)return'< 1 hour';if(h<24)return h+'h';return Math.floor(h/24)+'d '+h%24+'h';}

/* Stale */
let lastUpdateTs=Date.now();
function isStale(){return(Date.now()-lastUpdateTs)>120000;}
function updateStaleUI(){const b=document.getElementById('live-badge');if(!b)return;if(isStale()){b.classList.add('delayed');b.classList.remove('reconnecting');const st=document.getElementById('status-bar');if(st&&!st.querySelector('.stale-tag')){const t=document.createElement('span');t.className='stale-tag';t.textContent='STALE';st.prepend(t);}}else{b.classList.remove('delayed','reconnecting');const t=document.querySelector('.stale-tag');if(t)t.remove();}}

/* Clock */
setInterval(()=>{const e=document.getElementById('clock');if(e)e.textContent=new Date().toLocaleTimeString('en-GB');},1000);

/* API helper */
async function api(u){try{const r=await fetch(u,{cache:'no-store'});if(!r.ok)return null;return await r.json();}catch{return null;}}

/* ====================================================================
   §1  BINANCE SOURCE PROBE
   ==================================================================== */
const SOURCES=[
  {name:'Futures',rest:'https://fapi.binance.com',wss:'wss://fstream.binance.com/ws',type:'futures'},
  {name:'Spot',rest:'https://api.binance.com',wss:'wss://stream.binance.com:9443/ws',type:'spot'},
  {name:'Vision',rest:'https://data-api.binance.vision',wss:'wss://data-stream.binance.vision/ws',type:'spot'},
];
let activeSource=null;
const DEBUG=new URLSearchParams(location.search).has('debug');
const dbg_log=[];
function dbg(m){dbg_log.push('['+new Date().toISOString().slice(11,19)+'] '+m);if(dbg_log.length>60)dbg_log.shift();if(DEBUG)renderDebug();}
function renderDebug(){let p=document.getElementById('debug-panel');if(!p){p=document.createElement('div');p.id='debug-panel';p.style.cssText='position:fixed;bottom:0;right:0;width:400px;max-height:300px;overflow:auto;background:rgba(10,14,26,0.96);border:1px solid rgba(255,255,255,0.12);border-radius:12px 0 0 0;padding:12px;font:10px/1.6 var(--font-mono);color:#8b95a8;z-index:9999;';document.body.appendChild(p);}
p.innerHTML='<div style="color:#58a6ff;font-weight:700;margin-bottom:6px">🔧 DEBUG</div>'+
'<div>Source: <b style="color:#2dd4a8">'+(activeSource?activeSource.name:'probing')+'</b></div>'+
'<div>WS: <b>'+(ws?['CONNECTING','OPEN','CLOSING','CLOSED'][ws.readyState]:'none')+'</b></div>'+
'<div>Tracked: '+trackedSymbols.length+' | Markets: '+Object.keys(allMarkets).length+'</div>'+
'<hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:6px 0">'+
'<div style="max-height:160px;overflow-y:auto">'+dbg_log.map(l=>'<div>'+escHtml(l)+'</div>').join('')+'</div>';}

async function probeSource(){
  for(const src of SOURCES){
    const ep=src.type==='futures'?src.rest+'/fapi/v1/ticker/price?symbol=BTCUSDT':src.rest+'/api/v3/ticker/price?symbol=BTCUSDT';
    dbg('Probe '+src.name);
    try{const c=new AbortController();const t=setTimeout(()=>c.abort(),3000);const r=await fetch(ep,{signal:c.signal,cache:'no-store'});clearTimeout(t);if(r.ok){const d=await r.json();if(d&&d.price){activeSource=src;dbg('✓ '+src.name+' ok price='+d.price);return src;}}}
    catch(e){dbg('✗ '+src.name+': '+(e.name==='AbortError'?'timeout':e.message));}
  }
  dbg('All sources failed');return null;
}

/* ====================================================================
   §2  WEBSOCKET
   ==================================================================== */
let ws=null,wsDelay=1000,wsSubs=[];
function wsConnect(){
  if(!activeSource)return;dbg('WS connect '+activeSource.wss);
  try{ws=new WebSocket(activeSource.wss);}catch(e){dbg('WS error '+e.message);schedReconn();return;}
  ws.onopen=()=>{wsDelay=1000;dbg('WS open');if(wsSubs.length)wsSend({method:'SUBSCRIBE',params:wsSubs,id:1});updateBadge();};
  ws.onmessage=e=>{try{handleWS(JSON.parse(e.data));}catch{}};
  ws.onerror=()=>{dbg('WS error');};
  ws.onclose=e=>{dbg('WS closed '+e.code);schedReconn();updateBadge();};
}
function schedReconn(){setTimeout(()=>{wsDelay=Math.min(wsDelay*2,30000);wsConnect();},wsDelay);}
function wsSend(m){if(ws&&ws.readyState===1)ws.send(JSON.stringify(m));}
function wsSub(streams){if(wsSubs.length)wsSend({method:'UNSUBSCRIBE',params:wsSubs,id:2});wsSubs=streams;if(streams.length)wsSend({method:'SUBSCRIBE',params:streams,id:3});}
function updateBadge(){const b=document.getElementById('live-badge');if(!b)return;if(ws&&ws.readyState===1&&activeSource){b.innerHTML='<span class="live-dot"></span>LIVE · '+activeSource.name;b.classList.remove('delayed','reconnecting');}else{b.innerHTML='<span class="live-dot"></span>DELAYED';b.classList.add('delayed');b.classList.remove('reconnecting');}}

/* ====================================================================
   §3  STATE
   ==================================================================== */
let selectedAsset='BTCUSDT',selReqId=0,currentTF=localStorage.getItem('crypt_tf')||'5m';
let currentMiniType='funding',lastCryptoData=null,firstLoad=true;
let liveTickers={};   // {BTCUSDT:{price,chg,high,low,vol,open}}
let allMarkets={};    // {BTCUSDT:{price,chg,vol,base,...}}
let trackedSymbols=[];
let favorites=JSON.parse(localStorage.getItem('crypt_fav')||'[]');
let exchangeInfo={};  // {BTCUSDT:{pricePrecision,tickSize,...}}
let marketFilter='tracked',marketSort='pair',marketSortAsc=true,marketSearch='',marketSegment='crypto';
let marketsShowAll=false;
let isLogScale=false;
// Candle data for current chart
let chartCandles=[];
// AggTrade state
let aggTradeWs=null,largeTrades=[],largeTradeThreshold=250000;
let currentKlineSym=null;

/* ====================================================================
   §4  FEAR & GREED
   ==================================================================== */
function updateFG(val,lbl){const v=document.getElementById('fg-value'),l=document.getElementById('fg-label'),a=document.getElementById('fg-arc');if(v)v.textContent=val!=null?val:'--';if(l)l.textContent=lbl||'';if(a&&val!=null){const p=Math.min(Math.max(val/100,0),1);a.setAttribute('stroke-dasharray',(p*141.37).toFixed(1)+' 157');}}

/* ====================================================================
   §5  SPARKLINE
   ==================================================================== */
function drawSparkline(c,prices,color){if(!c||prices.length<2)return;const ctx=c.getContext('2d');const w=c.offsetWidth*(devicePixelRatio||1),h=c.offsetHeight*(devicePixelRatio||1);c.width=w;c.height=h;ctx.clearRect(0,0,w,h);const mn=Math.min(...prices),mx=Math.max(...prices),rng=mx-mn||1,py=h*.08;const x=i=>(i/(prices.length-1))*w,y=v=>py+(1-(v-mn)/rng)*(h-py*2);const g=ctx.createLinearGradient(0,0,0,h);g.addColorStop(0,color+'40');g.addColorStop(.6,color+'10');g.addColorStop(1,'transparent');ctx.beginPath();ctx.moveTo(x(0),y(prices[0]));for(let i=1;i<prices.length;i++)ctx.lineTo(x(i),y(prices[i]));ctx.lineTo(x(prices.length-1),h);ctx.lineTo(x(0),h);ctx.closePath();ctx.fillStyle=g;ctx.fill();ctx.beginPath();ctx.moveTo(x(0),y(prices[0]));for(let i=1;i<prices.length;i++)ctx.lineTo(x(i),y(prices[i]));ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineCap='round';ctx.lineJoin='round';ctx.stroke();}
async function loadSparkline(sym){const c=document.getElementById('spark-'+sym);if(!c)return;if(activeSource){try{const ep=activeSource.type==='futures'?activeSource.rest+'/fapi/v1/klines?symbol='+sym+'&interval=1h&limit=24':activeSource.rest+'/api/v3/klines?symbol='+sym+'&interval=1h&limit=24';const r=await fetch(ep,{cache:'no-store'});if(r.ok){const k=await r.json();if(k.length>=2){const p=k.map(x=>parseFloat(x[4]));drawSparkline(c,p,p[p.length-1]>=p[0]?'#2dd4a8':'#f85149');return;}}}catch{}}const d=await api('/api/candles?asset='+sym+'&hours=24');const cn=(d&&d.candles)||[];if(cn.length>=2){const p=cn.map(x=>x.price);drawSparkline(c,p,p[p.length-1]>=p[0]?'#2dd4a8':'#f85149');}}

/* ====================================================================
   §6  RENDER TRACKED STRIP
   ==================================================================== */
function renderTracked(data){
  const g=document.getElementById('tracked-strip');if(!g||!data.crypto)return;
  const list=data.crypto.filter(c=>c&&c.symbol);trackedSymbols=list.map(c=>c.symbol);
  const existing=g.querySelectorAll('.coin-card[data-symbol]');
  if(!existing.length){
    g.innerHTML=list.map((c,i)=>{
      const lv=liveTickers[c.symbol],ch=lv?lv.chg:(c.change_24h!==0?c.change_24h:null);
      const fr=c.funding_rate,lp=normPct(c.long_ratio),sp=lp!=null?(100-lp).toFixed(1):null,lpF=lp!=null?lp.toFixed(1):null;
      const pr=lv?lv.price:c.price;
      return '<div class="coin-card entry-in '+gainLoss(ch)+(c.symbol===selectedAsset?' active':'')+'" data-symbol="'+c.symbol+'" onclick="selectAsset(\''+c.symbol+'\')" style="animation-delay:'+(i*50)+'ms">'
        +'<div class="cc-top"><span class="cc-symbol">'+escHtml(c.symbol.replace('USDT',''))+'</span><span class="cc-change '+cls(ch)+' '+clsBg(ch)+'">'+(ch!=null?fmtPct(ch):'-')+'</span></div>'
        +'<div class="cc-price">'+fmtPrice(pr)+'</div>'
        +'<canvas class="cc-spark" id="spark-'+c.symbol+'"></canvas>'
        +'<div class="cc-meta"><span class="cc-tag '+cls(fr)+'">FR '+fmtFunding(fr)+'</span>'
        +(lpF!=null?'<span class="cc-tag">L/S '+lpF+'/'+sp+'</span>':'')
        +'</div></div>';
    }).join('');
    list.forEach(c=>loadSparkline(c.symbol));
    setTimeout(()=>g.querySelectorAll('.entry-in').forEach(e=>e.classList.remove('entry-in')),800);
  } else {
    list.forEach(c=>{
      const card=g.querySelector('[data-symbol="'+c.symbol+'"]');if(!card)return;
      const lv=liveTickers[c.symbol],ch=lv?lv.chg:(c.change_24h!==0?c.change_24h:null);
      const fr=c.funding_rate,lp=normPct(c.long_ratio),sp=lp!=null?(100-lp).toFixed(1):null,lpF=lp!=null?lp.toFixed(1):null;
      card.classList.remove('gain','loss','active');if(gainLoss(ch))card.classList.add(gainLoss(ch));if(c.symbol===selectedAsset)card.classList.add('active');
      const ce=card.querySelector('.cc-change');if(ce){ce.textContent=ch!=null?fmtPct(ch):'-';ce.className='cc-change '+cls(ch)+' '+clsBg(ch);}
      const pe=card.querySelector('.cc-price');if(pe)flashPrice(pe,pe.textContent,fmtPrice(lv?lv.price:c.price));
      const me=card.querySelector('.cc-meta');if(me)me.innerHTML='<span class="cc-tag '+cls(fr)+'">FR '+fmtFunding(fr)+'</span>'+(lpF!=null?'<span class="cc-tag">L/S '+lpF+'/'+sp+'</span>':'');
    });
  }
}

/* ====================================================================
   §7  MARKETS PANEL
   ==================================================================== */
async function loadAllMarkets(){
  if(!activeSource)return;
  try{
    // Exchange info for price precision
    const eiUrl=activeSource.type==='futures'?activeSource.rest+'/fapi/v1/exchangeInfo':activeSource.rest+'/api/v3/exchangeInfo';
    const eiR=await fetch(eiUrl,{cache:'no-store'});
    if(eiR.ok){const ei=await eiR.json();(ei.symbols||[]).forEach(s=>{
      if(s.quoteAsset==='USDT'&&s.status==='TRADING'&&(!s.contractType||s.contractType==='PERPETUAL')){
        const pp=s.pricePrecision||2;let ts=null;if(s.filters){const pf=s.filters.find(f=>f.filterType==='PRICE_FILTER');if(pf)ts=parseFloat(pf.tickSize);}
        exchangeInfo[s.symbol]={pricePrecision:pp,tickSize:ts,baseAsset:s.baseAsset};
      }
    });}

    // 24hr tickers
    const tkUrl=activeSource.type==='futures'?activeSource.rest+'/fapi/v1/ticker/24hr':activeSource.rest+'/api/v3/ticker/24hr';
    const tkR=await fetch(tkUrl,{cache:'no-store'});
    if(tkR.ok){const tks=await tkR.json();tks.forEach(t=>{
      if(!t.symbol||!t.symbol.endsWith('USDT'))return;
      const p=parseFloat(t.lastPrice||t.close||0),o=parseFloat(t.openPrice||t.open||0);
      allMarkets[t.symbol]={price:p,chg:o?((p-o)/o)*100:0,vol:parseFloat(t.quoteVolume||t.volume||0),base:(exchangeInfo[t.symbol]||{}).baseAsset||t.symbol.replace('USDT',''),high:parseFloat(t.highPrice||0),low:parseFloat(t.lowPrice||0)};
    });}
    dbg('Markets loaded: '+Object.keys(allMarkets).length);
  }catch(e){dbg('Markets load error: '+e.message);}
  renderMarkets();
}

function getFilteredMarkets(){
  let list=Object.entries(allMarkets).map(([sym,d])=>({sym,...d,isFav:favorites.includes(sym),isTracked:trackedSymbols.includes(sym)}));
  // Segment filter
  if(marketSegment==='forex'){
    // Forex from local API — handled separately
    return [];
  }
  // Search
  if(marketSearch){const q=marketSearch.toUpperCase();list=list.filter(m=>m.sym.includes(q)||m.base.includes(q));}
  // Filter
  switch(marketFilter){
    case'favorites':list=list.filter(m=>m.isFav);break;
    case'tracked':list=list.filter(m=>m.isTracked);break;
    case'gainers':list=list.filter(m=>m.chg>0).sort((a,b)=>b.chg-a.chg);break;
    case'losers':list=list.filter(m=>m.chg<0).sort((a,b)=>a.chg-b.chg);break;
    case'volume':list.sort((a,b)=>b.vol-a.vol);break;
    default:break;
  }
  // Sort (if not already sorted by filter)
  if(!['gainers','losers','volume'].includes(marketFilter)){
    const dir=marketSortAsc?1:-1;
    switch(marketSort){
      case'pair':list.sort((a,b)=>dir*a.sym.localeCompare(b.sym));break;
      case'price':list.sort((a,b)=>dir*(a.price-b.price));break;
      case'chg':list.sort((a,b)=>dir*(a.chg-b.chg));break;
      case'vol':list.sort((a,b)=>dir*(a.vol-b.vol));break;
    }
  }
  return list;
}

let lastMarketRender=0;
function renderMarkets(){
  const now=Date.now();if(now-lastMarketRender<200)return;lastMarketRender=now;
  const container=document.getElementById('markets-list');if(!container)return;

  if(marketSegment==='forex'){renderForexMarkets();return;}

  const list=getFilteredMarkets();
  const maxShow=marketsShowAll?list.length:60;
  const visible=list.slice(0,maxShow);

  let html='';
  visible.forEach(m=>{
    const pp=(exchangeInfo[m.sym]||{}).pricePrecision||2;
    const sel=m.sym===selectedAsset?' selected':'';
    html+='<div class="mrow'+sel+'" data-sym="'+m.sym+'" onclick="selectAsset(\''+m.sym+'\')">'
      +'<span class="mrow-pair"><span class="mrow-star'+(m.isFav?' fav':'')+'" onclick="event.stopPropagation();toggleFav(\''+m.sym+'\')">'+(m.isFav?'★':'☆')+'</span>'+escHtml(m.base)+'/USDT</span>'
      +'<span class="mrow-price mono">'+fmtPrice(m.price,pp)+'</span>'
      +'<span class="mrow-chg mono '+cls(m.chg)+'">'+fmtPct(m.chg)+'</span>'
      +'<span class="mrow-vol mono">'+fmtVol(m.vol)+'</span>'
      +'</div>';
  });
  if(!html)html='<div class="empty-state">No matching pairs</div>';
  container.innerHTML=html;

  const btn=document.getElementById('show-more-btn');
  if(btn){btn.style.display=list.length>maxShow?'':'none';}
}

function renderForexMarkets(){
  const container=document.getElementById('markets-list');if(!container)return;
  if(!lastCryptoData)return;
  // Forex data not in allMarkets, but from /api/summary forex
  container.innerHTML='<div class="empty-state">Forex data from /api/summary<br>Switch to Crypto for full market</div>';
}

function toggleFav(sym){const i=favorites.indexOf(sym);if(i>=0)favorites.splice(i,1);else favorites.push(sym);localStorage.setItem('crypt_fav',JSON.stringify(favorites));renderMarkets();}

/* Markets panel events */
document.addEventListener('DOMContentLoaded',()=>{
  // Search
  const searchEl=document.getElementById('market-search');
  if(searchEl)searchEl.addEventListener('input',e=>{marketSearch=e.target.value;renderMarkets();});
  // Pills
  document.querySelectorAll('.mpill').forEach(b=>b.addEventListener('click',()=>{
    document.querySelectorAll('.mpill').forEach(x=>x.classList.remove('active'));b.classList.add('active');
    marketFilter=b.dataset.filter;marketsShowAll=false;renderMarkets();
  }));
  // Sort
  document.querySelectorAll('.markets-table-head span').forEach(s=>s.addEventListener('click',()=>{
    const col=s.dataset.sort;if(marketSort===col)marketSortAsc=!marketSortAsc;else{marketSort=col;marketSortAsc=true;}renderMarkets();
  }));
  // Show more
  const smBtn=document.getElementById('show-more-btn');
  if(smBtn)smBtn.addEventListener('click',()=>{marketsShowAll=true;renderMarkets();});
  // Segment switch
  document.querySelectorAll('.seg-btn').forEach(b=>b.addEventListener('click',()=>{
    document.querySelectorAll('.seg-btn').forEach(x=>x.classList.remove('active'));b.classList.add('active');
    marketSegment=b.dataset.seg;renderMarkets();
  }));
  // Timeframe pills
  document.querySelectorAll('.tf-pill').forEach(b=>b.addEventListener('click',()=>{
    document.querySelectorAll('.tf-pill').forEach(x=>x.classList.remove('active'));b.classList.add('active');
    currentTF=b.dataset.tf;localStorage.setItem('crypt_tf',currentTF);
    selectAsset(selectedAsset);
  }));
  // Restore saved TF
  const savedTF=document.querySelector('.tf-pill[data-tf="'+currentTF+'"]');
  if(savedTF){document.querySelectorAll('.tf-pill').forEach(x=>x.classList.remove('active'));savedTF.classList.add('active');}
  // Chart buttons
  document.getElementById('btn-log')?.addEventListener('click',toggleLogScale);
  document.getElementById('btn-reset')?.addEventListener('click',()=>{if(lwChart)lwChart.timeScale().fitContent();});
  document.getElementById('btn-fullscreen')?.addEventListener('click',toggleFullscreen);
  document.getElementById('btn-jump')?.addEventListener('click',jumpToRealtime);
  // Tab indicator init
  const at=document.querySelector('.tab-btn.active');if(at)updateTabIndicator(at);
  // News drawer close
  document.getElementById('drawer-close')?.addEventListener('click',closeDrawer);
  document.getElementById('news-drawer-overlay')?.addEventListener('click',closeDrawer);
  document.getElementById('drawer-prev')?.addEventListener('click',()=>navDrawer(-1));
  document.getElementById('drawer-next')?.addEventListener('click',()=>navDrawer(1));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();});
  // Whale threshold pills
  document.addEventListener('click',e=>{const tp=e.target.closest('.threshold-pill');if(tp){document.querySelectorAll('.threshold-pill').forEach(x=>x.classList.remove('active'));tp.classList.add('active');largeTradeThreshold=parseInt(tp.dataset.val);largeTrades=[];renderLargeTrades();}});
});

/* ====================================================================
   §8  SELECT ASSET
   ==================================================================== */
async function selectAsset(sym){
  selectedAsset=sym;const rid=++selReqId;
  // Update cards
  document.querySelectorAll('.coin-card').forEach(c=>c.classList.toggle('active',c.dataset.symbol===sym));
  document.querySelectorAll('.mrow').forEach(r=>{r.classList.toggle('selected',r.dataset.sym===sym);});

  const base=sym.replace('USDT','');
  document.getElementById('detail-symbol').textContent=base;

  // Check if forex
  const isForex=!sym.endsWith('USDT');

  // Price
  const lv=liveTickers[sym];const pe=document.getElementById('detail-price');
  const pp=(exchangeInfo[sym]||{}).pricePrecision;
  if(lv){flashPrice(pe,pe.textContent,fmtPrice(lv.price,pp));const ce=document.getElementById('detail-change');ce.textContent=fmtPct(lv.chg);ce.className='detail-chg mono '+cls(lv.chg)+' '+clsBg(lv.chg);}
  else if(lastCryptoData){const coin=lastCryptoData.find(c=>c.symbol===sym);if(coin){flashPrice(pe,pe.textContent,fmtPrice(coin.price,pp));}}

  // Title
  const titleP=lv?fmtPrice(lv.price,pp):'';
  document.title=base+' '+titleP+' - CrypT';

  // Destroy chart
  destroyChart();showChartSkeleton();

  // Subscribe kline
  subKline(sym);

  // Fetch data
  const isTracked=trackedSymbols.includes(sym);
  const derivP=isTracked?api('/api/derivatives?asset='+sym):null;
  const crossP=isTracked?api('/api/cross-exchange?asset='+sym):null;
  const candleP=fetchKlines(sym,currentTF,300);

  const [derivResp,crossResp,klines]=await Promise.all([derivP,crossP,candleP]);
  if(rid!==selReqId)return;

  // Tiles visibility
  const notice=document.getElementById('tracked-notice');
  const tilesSec=document.getElementById('sec-tiles');
  if(!isTracked&&notice){notice.style.display='';} else if(notice){notice.style.display='none';}

  // Derivatives
  if(isTracked&&derivResp&&derivResp.derivatives){
    const d=derivResp.derivatives;
    const frEl=document.getElementById('d-funding');frEl.textContent=fmtFunding(d.funding_rate);frEl.className='tile-value mono '+cls(d.funding_rate);
    document.getElementById('d-funding-sub').textContent='8h cycle';
    document.getElementById('d-oi').textContent=fmtUSD(d.open_interest);
    const oiEl=document.getElementById('d-oi-chg');oiEl.textContent=fmtPct(d.oi_change_1h);oiEl.className='tile-value mono '+cls(d.oi_change_1h);
    const lsr=d.long_short_ratio||{};
    document.getElementById('d-long-pct').textContent=lsr.long_pct!=null?fmt(lsr.long_pct,1)+'%':'—';
    document.getElementById('d-short-pct').textContent=lsr.short_pct!=null?fmt(lsr.short_pct,1)+'%':'—';
    document.getElementById('ls-long-bar').style.width=(lsr.long_pct||50)+'%';
    // Cross-exchange
    if(crossResp&&crossResp.exchanges){const ex=crossResp.exchanges,by=ex.find(e=>e.exchange==='bybit');const bnFr=derivResp.snapshot?derivResp.snapshot.funding_rate:null,byFr=by?by.funding_rate:null,sp=bnFr!=null&&byFr!=null?bnFr-byFr:null;
    const be=document.getElementById('d-binance-fr');be.textContent=fmtFunding(bnFr);be.className='mono '+cls(bnFr);
    const ye=document.getElementById('d-bybit-fr');ye.textContent=fmtFunding(byFr);ye.className='mono '+cls(byFr);
    const se=document.getElementById('d-spread');se.textContent=fmtFunding(sp);se.className='mono '+cls(sp);}
  } else if(!isTracked&&activeSource){
    // Fetch from Binance for non-tracked
    await loadBinanceDerivatives(sym);
  }

  // Chart
  if(klines&&klines.length>0){chartCandles=klines;renderChart(klines);}
  else{const ld=await api('/api/candles?asset='+sym+'&hours=48');if(rid!==selReqId)return;if(ld&&ld.candles&&ld.candles.length)renderChartLocal(ld.candles);else showChartError('No chart data');}

  // Mini chart
  if(isTracked)loadMiniChart(sym,currentMiniType);
  // Start aggTrade for large trades
  connectAggTrade(sym);
}

async function loadBinanceDerivatives(sym){
  if(!activeSource||activeSource.type!=='futures')return;
  try{
    const [piR,oiR,lsR]=await Promise.all([
      fetch(activeSource.rest+'/fapi/v1/premiumIndex?symbol='+sym,{cache:'no-store'}).then(r=>r.json()).catch(()=>null),
      fetch(activeSource.rest+'/fapi/v1/openInterest?symbol='+sym,{cache:'no-store'}).then(r=>r.json()).catch(()=>null),
      fetch(activeSource.rest+'/futures/data/globalLongShortAccountRatio?symbol='+sym+'&period=5m&limit=1',{cache:'no-store'}).then(r=>r.json()).catch(()=>null),
    ]);
    if(piR){document.getElementById('d-funding').textContent=fmtFunding(parseFloat(piR.lastFundingRate));document.getElementById('d-funding').className='tile-value mono '+cls(parseFloat(piR.lastFundingRate));}
    if(oiR){document.getElementById('d-oi').textContent=fmtUSD(parseFloat(oiR.openInterest)*((liveTickers[sym]||{}).price||0));}
    if(lsR&&lsR[0]){const lr=parseFloat(lsR[0].longAccount)*100,sr=parseFloat(lsR[0].shortAccount)*100;
      document.getElementById('d-long-pct').textContent=fmt(lr,1)+'%';document.getElementById('d-short-pct').textContent=fmt(sr,1)+'%';document.getElementById('ls-long-bar').style.width=lr+'%';}
  }catch(e){dbg('Binance deriv error: '+e.message);}
}

/* ====================================================================
   §9  KLINES & CHART
   ==================================================================== */
async function fetchKlines(sym,tf,limit){
  if(!activeSource)return null;
  try{const ep=activeSource.type==='futures'?activeSource.rest+'/fapi/v1/klines?symbol='+sym+'&interval='+tf+'&limit='+limit:activeSource.rest+'/api/v3/klines?symbol='+sym+'&interval='+tf+'&limit='+limit;
  const r=await fetch(ep,{cache:'no-store'});if(!r.ok)return null;
  return(await r.json()).map(k=>({time:Math.floor(k[0]/1000),open:+k[1],high:+k[2],low:+k[3],close:+k[4],volume:+k[5]}));}
  catch(e){dbg('Klines error: '+e.message);return null;}
}

function subKline(sym){
  currentKlineSym=sym;const s=sym.toLowerCase();
  // All tracked miniTickers + kline for selected
  const streams=trackedSymbols.map(t=>t.toLowerCase()+'@miniTicker');
  streams.push(s+'@kline_'+currentTF);
  wsSub(streams);
}

/* Chart instances */
let lwChart=null,lwCandleSeries=null,lwVolSeries=null,lwMA7=null,lwMA25=null,lwMA99=null,lwResize=null;

function destroyChart(){if(lwResize)lwResize.disconnect();if(lwChart)lwChart.remove();lwChart=lwCandleSeries=lwVolSeries=lwMA7=lwMA25=lwMA99=lwResize=null;}

function showChartSkeleton(){const c=document.getElementById('chart-container');if(c)c.innerHTML='<div class="chart-skeleton"><div class="skeleton-block" style="height:100%;border-radius:12px"></div></div>';}
function showChartError(msg){const c=document.getElementById('chart-container');if(c)c.innerHTML='<div class="chart-error-card"><div style="font-size:32px;margin-bottom:12px">📊</div><div style="font-size:14px;font-weight:600;margin-bottom:6px">'+escHtml(msg)+'</div><button class="retry-btn" onclick="selectAsset(selectedAsset)">⟳ Retry</button></div>';}

function computeMA(data,period){const r=[];for(let i=0;i<data.length;i++){if(i<period-1){r.push({time:data[i].time,value:NaN});continue;}let s=0;for(let j=i-period+1;j<=i;j++)s+=data[j].close;r.push({time:data[i].time,value:s/period});}return r.filter(d=>!isNaN(d.value));}

function renderChart(klines){
  const c=document.getElementById('chart-container');if(!c||!klines.length)return showChartError('No data');
  c.innerHTML='';c.style.minHeight='420px';
  const pp=(exchangeInfo[selectedAsset]||{}).pricePrecision||2;
  const ts=(exchangeInfo[selectedAsset]||{}).tickSize;
  const priceFormat=ts?{type:'price',precision:pp,minMove:ts}:{type:'price',precision:pp,minMove:Math.pow(10,-pp)};

  lwChart=LightweightCharts.createChart(c,{...chartOpts(),width:c.clientWidth,height:c.clientHeight||420});

  lwCandleSeries=lwChart.addCandlestickSeries({upColor:'#2dd4a8',downColor:'#f85149',borderUpColor:'#2dd4a8',borderDownColor:'#f85149',wickUpColor:'rgba(45,212,168,0.5)',wickDownColor:'rgba(248,81,73,0.5)',priceFormat});
  lwCandleSeries.setData(klines.map(k=>({time:k.time,open:k.open,high:k.high,low:k.low,close:k.close})));

  // Volume
  lwVolSeries=lwChart.addHistogramSeries({color:'#58a6ff',priceFormat:{type:'volume'},priceScaleId:'vol'});
  lwChart.priceScale('vol').applyOptions({scaleMargins:{top:0.82,bottom:0}});
  lwVolSeries.setData(klines.map(k=>({time:k.time,value:k.volume,color:k.close>=k.open?'rgba(45,212,168,0.25)':'rgba(248,81,73,0.25)'})));

  // MAs
  const ma7=computeMA(klines,7),ma25=computeMA(klines,25),ma99=computeMA(klines,99);
  lwMA7=lwChart.addLineSeries({color:'#f7931a',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  lwMA25=lwChart.addLineSeries({color:'#58a6ff',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  lwMA99=lwChart.addLineSeries({color:'#bc8cff',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
  if(ma7.length)lwMA7.setData(ma7);if(ma25.length)lwMA25.setData(ma25);if(ma99.length)lwMA99.setData(ma99);

  lwChart.timeScale().fitContent();

  // Crosshair legend
  lwChart.subscribeCrosshairMove(param=>{
    const last=klines[klines.length-1];
    if(!param||!param.time){updateLegend(last,klines);return;}
    const idx=klines.findIndex(k=>k.time===param.time);
    if(idx>=0)updateLegend(klines[idx],klines,idx);else updateLegend(last,klines);
  });

  // Scroll to left → load more history
  lwChart.timeScale().subscribeVisibleLogicalRangeChange(range=>{
    if(!range)return;
    const jmp=document.getElementById('btn-jump');
    if(jmp){jmp.style.display=range.to<klines.length-5?'':'none';}
    if(range.from<2)loadOlderHistory();
  });

  // Resize
  lwResize=new ResizeObserver(es=>{for(const e of es){const{width:w,height:h}=e.contentRect;if(lwChart&&w>0&&h>0)lwChart.resize(w,h);}});
  lwResize.observe(c);

  // Update legend with latest
  updateLegend(klines[klines.length-1],klines);

  // Log scale
  if(isLogScale)lwChart.priceScale('right').applyOptions({mode:1});
}

function chartOpts(){return{layout:{background:{type:'solid',color:'transparent'},textColor:'#4a5068',fontFamily:"'JetBrains Mono',monospace",fontSize:10},grid:{vertLines:{color:'rgba(255,255,255,0.03)'},horzLines:{color:'rgba(255,255,255,0.03)'}},crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:'rgba(88,166,255,0.3)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#0e1525'},horzLine:{color:'rgba(88,166,255,0.3)',width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:'#0e1525'}},rightPriceScale:{borderColor:'transparent',scaleMargins:{top:0.08,bottom:0.22}},timeScale:{borderColor:'transparent',timeVisible:true,secondsVisible:false,rightOffset:5,barSpacing:8},handleScroll:{mouseWheel:true,pressedMouseMove:true},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}};}

function updateLegend(candle,all,idx){
  if(!candle)return;const pp=(exchangeInfo[selectedAsset]||{}).pricePrecision||2;
  document.getElementById('leg-o').textContent=candle.open.toFixed(pp);
  document.getElementById('leg-h').textContent=candle.high.toFixed(pp);
  document.getElementById('leg-l').textContent=candle.low.toFixed(pp);
  document.getElementById('leg-c').textContent=candle.close.toFixed(pp);
  const ch=candle.open?((candle.close-candle.open)/candle.open*100):0;
  const chEl=document.getElementById('leg-chg');chEl.textContent=fmtPct(ch);chEl.className='leg-item leg-chg '+cls(ch);
  document.getElementById('leg-vol').textContent=fmtVol(candle.volume);
  // MAs
  const i=idx!=null?idx:all.length-1;
  const ma=(p)=>{if(i<p-1)return'—';let s=0;for(let j=i-p+1;j<=i;j++)s+=all[j].close;return(s/p).toFixed(pp);};
  document.getElementById('leg-ma7').textContent=ma(7);
  document.getElementById('leg-ma25').textContent=ma(25);
  document.getElementById('leg-ma99').textContent=ma(99);
}

function renderChartLocal(candles){
  const c=document.getElementById('chart-container');if(!c||!candles.length)return showChartError('No data');
  c.innerHTML='';c.style.minHeight='420px';
  lwChart=LightweightCharts.createChart(c,{...chartOpts(),width:c.clientWidth,height:c.clientHeight||420});
  const ls=lwChart.addLineSeries({color:'#58a6ff',lineWidth:2,crosshairMarkerVisible:true});
  const d=candles.filter(x=>x.timestamp&&x.price!=null).map(x=>({time:x.timestamp,value:+x.price})).sort((a,b)=>a.time-b.time);
  if(!d.length)return showChartError('No data');
  ls.setData(d);lwChart.timeScale().fitContent();
  lwResize=new ResizeObserver(es=>{for(const e of es){const{width:w,height:h}=e.contentRect;if(lwChart&&w>0&&h>0)lwChart.resize(w,h);}});
  lwResize.observe(c);
}

let loadingHistory=false;
async function loadOlderHistory(){
  if(loadingHistory||!chartCandles.length)return;loadingHistory=true;
  const oldest=chartCandles[0].time*1000-1;
  const ep=activeSource.type==='futures'?activeSource.rest+'/fapi/v1/klines?symbol='+selectedAsset+'&interval='+currentTF+'&endTime='+oldest+'&limit=500':activeSource.rest+'/api/v3/klines?symbol='+selectedAsset+'&interval='+currentTF+'&endTime='+oldest+'&limit=500';
  try{const r=await fetch(ep,{cache:'no-store'});if(r.ok){const raw=await r.json();const older=raw.map(k=>({time:Math.floor(k[0]/1000),open:+k[1],high:+k[2],low:+k[3],close:+k[4],volume:+k[5]}));
    if(older.length){chartCandles=[...older,...chartCandles];if(lwCandleSeries)lwCandleSeries.setData(chartCandles.map(k=>({time:k.time,open:k.open,high:k.high,low:k.low,close:k.close})));
    if(lwVolSeries)lwVolSeries.setData(chartCandles.map(k=>({time:k.time,value:k.volume,color:k.close>=k.open?'rgba(45,212,168,0.25)':'rgba(248,81,73,0.25)'})));
    const ma7=computeMA(chartCandles,7),ma25=computeMA(chartCandles,25),ma99=computeMA(chartCandles,99);
    if(lwMA7&&ma7.length)lwMA7.setData(ma7);if(lwMA25&&ma25.length)lwMA25.setData(ma25);if(lwMA99&&ma99.length)lwMA99.setData(ma99);
    dbg('Loaded '+older.length+' older candles');}}}catch(e){dbg('History load error: '+e.message);}
  loadingHistory=false;
}

function toggleLogScale(){isLogScale=!isLogScale;const btn=document.getElementById('btn-log');if(btn)btn.classList.toggle('active',isLogScale);if(lwChart)lwChart.priceScale('right').applyOptions({mode:isLogScale?1:0});}
function toggleFullscreen(){const el=document.querySelector('.tile-chart');if(!el)return;if(document.fullscreenElement)document.exitFullscreen();else el.requestFullscreen();}
function jumpToRealtime(){if(lwChart)lwChart.timeScale().scrollToRealTime();document.getElementById('btn-jump').style.display='none';}

/* Candle countdown */
setInterval(()=>{const el=document.getElementById('candle-countdown');if(!el||!chartCandles.length)return;
  const tfMs={'1m':60,'3m':180,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400,'1D':86400,'1W':604800};
  const sec=tfMs[currentTF]||300;const last=chartCandles[chartCandles.length-1];
  const closeAt=last.time+sec;const rem=closeAt-Math.floor(Date.now()/1000);
  if(rem>0){const m=Math.floor(rem/60),s=rem%60;el.textContent=m+':'+(s<10?'0':'')+s;}else{el.textContent='';}
},1000);

/* ====================================================================
   §10  WS MESSAGE HANDLER
   ==================================================================== */
function handleWS(data){
  if(!data||data.result!==undefined)return;
  if(Array.isArray(data)){data.forEach(processTicker);return;}
  if(data.e==='24hrMiniTicker'){processTicker(data);return;}
  if(data.e==='kline'){processKline(data);return;}
}

function processTicker(d){
  const sym=d.s;if(!sym)return;
  const o=+d.o,c=+d.c,ch=o?((c-o)/o)*100:0;
  liveTickers[sym]={price:c,chg:ch,high:+d.h,low:+d.l,vol:+(d.q||d.v),open:o};
  // Update allMarkets
  if(allMarkets[sym]){allMarkets[sym].price=c;allMarkets[sym].chg=ch;allMarkets[sym].vol=+(d.q||d.v);}
  // Update tracked card
  const card=document.querySelector('.tracked-strip .coin-card[data-symbol="'+sym+'"]');
  if(card){const pe=card.querySelector('.cc-price');if(pe)flashPrice(pe,pe.textContent,fmtPrice(c));
    const ce=card.querySelector('.cc-change');if(ce){ce.textContent=fmtPct(ch);ce.className='cc-change '+cls(ch)+' '+clsBg(ch);}
    card.classList.remove('gain','loss');if(gainLoss(ch))card.classList.add(gainLoss(ch));}
  // Update detail if selected
  if(sym===selectedAsset){const pe=document.getElementById('detail-price'),ce=document.getElementById('detail-change');
    const pp=(exchangeInfo[sym]||{}).pricePrecision;
    if(pe)flashPrice(pe,pe.textContent,fmtPrice(c,pp));if(ce){ce.textContent=fmtPct(ch);ce.className='detail-chg mono '+cls(ch)+' '+clsBg(ch);}
    document.title=sym.replace('USDT','')+' '+fmtPrice(c,pp)+' - CrypT';}
  lastUpdateTs=Date.now();
}

function processKline(data){
  const k=data.k;if(!k||!lwCandleSeries||k.s!==currentKlineSym)return;
  const candle={time:Math.floor(k.t/1000),open:+k.o,high:+k.h,low:+k.l,close:+k.c,volume:+k.v};
  // Update or append
  if(chartCandles.length){const last=chartCandles[chartCandles.length-1];
    if(candle.time===last.time){chartCandles[chartCandles.length-1]=candle;}
    else if(candle.time>last.time){chartCandles.push(candle);}}
  lwCandleSeries.update({time:candle.time,open:candle.open,high:candle.high,low:candle.low,close:candle.close});
  if(lwVolSeries)lwVolSeries.update({time:candle.time,value:candle.volume,color:candle.close>=candle.open?'rgba(45,212,168,0.25)':'rgba(248,81,73,0.25)'});
  // Update last MA point only
  if(chartCandles.length>=7&&lwMA7){const s=chartCandles.slice(-7);const v=s.reduce((a,c)=>a+c.close,0)/7;lwMA7.update({time:candle.time,value:v});}
  if(chartCandles.length>=25&&lwMA25){const s=chartCandles.slice(-25);const v=s.reduce((a,c)=>a+c.close,0)/25;lwMA25.update({time:candle.time,value:v});}
  if(chartCandles.length>=99&&lwMA99){const s=chartCandles.slice(-99);const v=s.reduce((a,c)=>a+c.close,0)/99;lwMA99.update({time:candle.time,value:v});}
  // Update legend
  updateLegend(candle,chartCandles);
}

/* ====================================================================
   §11  MINI CHART
   ==================================================================== */
let miniLw=null,miniS=null,miniRO=null;
async function loadMiniChart(sym,type){const ep=type==='funding'?'/api/funding-history':'/api/oi-history';const d=await api(ep+'?asset='+(sym||selectedAsset));if(!d||!d.history)return;const c=document.getElementById('mini-chart-container');if(!c)return;const items=d.history.filter(h=>h!=null);const color=type==='funding'?'#bc8cff':'#58a6ff';const cd=items.map(h=>{const v=type==='funding'?(h.funding_rate!=null?h.funding_rate:h.rate):(h.open_interest);if(v==null)return null;return{time:h.timestamp,value:+v};}).filter(Boolean).sort((a,b)=>a.time-b.time);if(!cd.length)return;if(miniLw){if(miniRO)miniRO.disconnect();miniLw.remove();miniLw=miniS=null;}
miniLw=LightweightCharts.createChart(c,{width:c.clientWidth,height:c.clientHeight||80,layout:{background:{type:'solid',color:'transparent'},textColor:'#4a5068',fontFamily:"'JetBrains Mono',monospace",fontSize:9},grid:{vertLines:{visible:false},horzLines:{color:'rgba(255,255,255,0.02)'}},crosshair:{mode:LightweightCharts.CrosshairMode.Magnet},rightPriceScale:{borderColor:'transparent',scaleMargins:{top:0.1,bottom:0.05}},timeScale:{visible:false},handleScroll:false,handleScale:false});
miniS=miniLw.addLineSeries({color,lineWidth:1.5,crosshairMarkerVisible:false,lastValueVisible:false,priceLineVisible:false});miniS.setData(cd);miniLw.timeScale().fitContent();
miniRO=new ResizeObserver(es=>{for(const e of es){const{width:w,height:h}=e.contentRect;if(miniLw&&w>0&&h>0)miniLw.resize(w,h);}});miniRO.observe(c);}
function switchMiniChart(t,b){currentMiniType=t;document.querySelectorAll('.mini-tab').forEach(x=>x.classList.remove('active'));if(b)b.classList.add('active');loadMiniChart(selectedAsset,t);}

/* ====================================================================
   §12  TABS
   ==================================================================== */
function switchTab(name,btn){document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));const p=document.getElementById('tab-'+name);if(p)p.classList.add('active');if(btn)btn.classList.add('active');updateTabIndicator(btn);}
function updateTabIndicator(btn){const ind=document.getElementById('tab-indicator');if(!ind||!btn)return;ind.style.left=btn.offsetLeft+'px';ind.style.width=btn.offsetWidth+'px';}

/* ====================================================================
   §13  NEWS (Step 4) — Drawer
   ==================================================================== */
let newsItems=[],drawerIdx=-1;
function renderNews(news){
  newsItems=news;const el=document.getElementById('tab-news');if(!el)return;
  let html='';
  // Stale check
  if(news.length>0){const newest=news[0].timestamp;const hoursAgo=(Date.now()/1000-newest)/3600;
    if(hoursAgo>6)html+='<div class="news-stale-chip">Last news '+agoLong(newest)+' ago — collector may be stopped</div>';}
  if(!news.length){el.innerHTML='<div class="empty-state">No news available</div>';return;}
  html+=news.map((n,i)=>{const title=escHtml(n.headline||n.title||'');const src=escHtml(n.source||'');const time=ago(n.timestamp);
    return '<div class="news-item" onclick="openDrawer('+i+')"><div class="title">'+title+'</div><div class="source">'+src+(time?' · '+time:'')+'</div></div>';}).join('');
  el.innerHTML=html;
}
function openDrawer(idx){
  drawerIdx=idx;const n=newsItems[idx];if(!n)return;
  document.getElementById('drawer-title').textContent=n.headline||n.title||'';
  document.getElementById('drawer-meta').textContent=(n.source||'')+(n.timestamp?' · '+ago(n.timestamp):'');
  const content=n.summary||n.description||n.content||'No summary available for this article.';
  document.getElementById('drawer-content').textContent=content;
  const link=document.getElementById('drawer-link');link.href=safeHref(n.url||n.link);
  document.getElementById('news-drawer').classList.add('open');
  document.getElementById('news-drawer-overlay').classList.add('open');
  updateDrawerNav();
}
function closeDrawer(){document.getElementById('news-drawer').classList.remove('open');document.getElementById('news-drawer-overlay').classList.remove('open');}
function navDrawer(dir){const ni=drawerIdx+dir;if(ni>=0&&ni<newsItems.length)openDrawer(ni);}
function updateDrawerNav(){document.getElementById('drawer-prev').disabled=drawerIdx<=0;document.getElementById('drawer-next').disabled=drawerIdx>=newsItems.length-1;}

/* ====================================================================
   §14  WHALE (Step 5) — Large Trades
   ==================================================================== */
function renderWhale(whales){
  const el=document.getElementById('tab-whale');if(!el)return;
  let html='';
  if(!whales||!whales.length){html+='<div class="empty-state" style="margin-bottom:12px">No on-chain whale data<br><small>(Whale Alert API key not configured)</small></div>';}
  else{html+=whales.map(w=>'<div class="whale-item"><span class="wh-sym">'+escHtml(w.symbol||'')+'</span><span class="wh-flow">'+escHtml(w.flow_type||w.type||'')+'</span><span class="wh-amt mono">'+fmtUSD(w.amount||w.value)+'</span><span class="wh-time">'+ago(w.timestamp)+'</span></div>').join('');}
  // Large trades sub-section
  html+='<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--glass-border)">';
  html+='<div class="ltrade-header"><span class="ltrade-label">Exchange Large Trades ('+selectedAsset.replace('USDT','')+')</span>';
  html+='<div class="threshold-pills">';
  [100000,250000,500000,1000000].forEach(v=>{html+='<button class="threshold-pill'+(v===largeTradeThreshold?' active':'')+'" data-val="'+v+'">'+fmtUSD(v).replace('$','')+'</button>';});
  html+='</div></div>';
  html+='<div style="font-size:9px;color:var(--text-3);margin-bottom:6px">Exchange large trades, not on-chain transfers</div>';
  html+='<div id="large-trades-list">';
  html+=renderLargeTradesHTML();
  html+='</div></div>';
  el.innerHTML=html;
}

function renderLargeTrades(){const el=document.getElementById('large-trades-list');if(el)el.innerHTML=renderLargeTradesHTML();}
function renderLargeTradesHTML(){
  if(!largeTrades.length)return'<div class="empty-state" style="padding:10px">Waiting for large trades…</div>';
  return largeTrades.slice(0,50).map(t=>{
    const time=new Date(t.time).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
    const side=t.isSeller?'SELL':'BUY';const sc=t.isSeller?'down':'up';
    return'<div class="ltrade-row"><span class="ltrade-time">'+time+'</span><span class="ltrade-side '+sc+'">'+side+'</span><span class="ltrade-size mono">'+fmtUSD(t.usdVal)+'</span><span class="ltrade-price mono">'+fmtPrice(t.price)+'</span></div>';
  }).join('');
}

function connectAggTrade(sym){
  if(aggTradeWs){aggTradeWs.close();aggTradeWs=null;}
  largeTrades=[];
  if(!activeSource)return;
  const url=activeSource.wss.replace('/ws','/ws/'+sym.toLowerCase()+'@aggTrade');
  try{aggTradeWs=new WebSocket(url);
    aggTradeWs.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.e==='aggTrade'){const price=+d.p,qty=+d.q,usd=price*qty;if(usd>=largeTradeThreshold){largeTrades.unshift({time:d.T||d.E,price,qty,usdVal:usd,isSeller:d.m});if(largeTrades.length>50)largeTrades.pop();renderLargeTrades();}}}catch{}};
    aggTradeWs.onerror=()=>{};
    aggTradeWs.onclose=()=>{};
  }catch{}
}

/* ====================================================================
   §15  CALENDAR (Step 5)
   ==================================================================== */
function renderCalendar(events){
  const el=document.getElementById('tab-calendar');if(!el)return;
  let html='';
  // Filter chips
  html+='<div class="cal-filter-chips"><button class="cal-chip active" onclick="filterCal(\'all\',this)">All</button><button class="cal-chip" onclick="filterCal(\'high\',this)">High</button></div>';
  if(!events||!events.length){
    html+='<div class="empty-state">No upcoming events in the 72h window</div>';
    html+='<div class="cal-latest-info">Calendar data may not be available — collectors may need to be running</div>';
    el.innerHTML=html;return;
  }
  const now=Date.now()/1000;
  html+=events.map(e=>{
    const imp=(e.importance||'').toLowerCase();const cla=imp==='high'?'high':imp==='medium'?'medium':'low';
    const isPast=e.timestamp&&e.timestamp<now;
    const dots='<span class="ev-impact">'+'<span class="ev-dot" style="background:'+(imp==='high'?'var(--red)':imp==='medium'?'var(--yellow)':'var(--text-3)')+'"></span>'.repeat(imp==='high'?3:imp==='medium'?2:1)+'</span>';
    const countdown=e.timestamp&&!isPast?'<span style="color:var(--yellow);font-size:9px;margin-left:6px">in '+agoLong(now-(e.timestamp-now))+'</span>':'';
    return'<div class="cal-item '+cla+(isPast?' past':'')+'"><div class="ev-info">'+dots+'<span class="ev-cur">'+escHtml(e.currency||'')+'</span><span class="ev-title">'+escHtml(e.title||e.event||'')+'</span>'+countdown+'</div><span class="ev-time mono">'+escHtml(e.time||'')+'</span></div>';
  }).join('');
  el.innerHTML=html;
}
function filterCal(type,btn){document.querySelectorAll('.cal-chip').forEach(x=>x.classList.remove('active'));if(btn)btn.classList.add('active');/* TODO: re-filter */}

/* ====================================================================
   §16  SIGNALS & DB STATS
   ==================================================================== */
function renderSignals(sigs,acc){const el=document.getElementById('signals-content');if(!el)return;let h='';if(acc&&acc.total_signals>0){h+='<div style="margin-bottom:14px"><table class="stat-table"><tr><td>Total Signals</td><td>'+acc.total_signals+'</td></tr><tr><td>Win Rate</td><td class="'+(acc.win_rate>=50?'up':'down')+'">'+fmtPct(acc.win_rate)+'</td></tr><tr><td>Avg Confidence</td><td>'+fmtPct(acc.avg_confidence)+'</td></tr></table></div>';}
if(sigs&&sigs.length){h+=sigs.map(s=>{const d=s.direction||s.signal||'—';const up=d.toLowerCase().match(/long|buy|up/);const cc=up?'up':'down';const ar=up?'▲':'▼';const pr=s.probability!=null?fmt(s.probability*100,1)+'%':'—';return'<div class="signal-card"><div style="display:flex;justify-content:space-between"><span class="sig-dir '+cc+'">'+ar+' '+escHtml(d)+'</span><span class="sig-prob mono">'+pr+'</span></div><div class="sig-meta">'+escHtml(s.symbol||'')+(s.outcome?' · '+escHtml(s.outcome):'')+(s.timestamp?' · '+ago(s.timestamp):'')+'</div></div>';}).join('');}
else{h='<div class="empty-state"><span>🤖 Model is collecting data…</span><small>Needs ~300+ snapshots per asset</small></div>';}el.innerHTML=h;}

function renderDBStats(st){const el=document.getElementById('tab-dbstats');if(!el||!st)return;let h='<table class="stat-table">';
['snapshots','news_items','whale_transactions','signals','economic_events','cross_exchange_funding','subscribers','db_size_mb'].forEach(k=>{if(st[k]!=null)h+='<tr><td>'+k.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())+'</td><td>'+(k==='db_size_mb'?st[k]+' MB':Number(st[k]).toLocaleString())+'</td></tr>';});
h+='</table>';el.innerHTML=h;}

/* ====================================================================
   §17  SCROLL SPY
   ==================================================================== */
function updateScrollSpy(){const secs=document.querySelectorAll('section[id]');let act='';const sy=window.scrollY+100;secs.forEach(s=>{if(s.offsetTop<=sy)act=s.id;});document.querySelectorAll('.rail-link').forEach(l=>l.classList.toggle('active',l.getAttribute('data-section')===act));}
window.addEventListener('scroll',updateScrollSpy,{passive:true});

/* ====================================================================
   §18  POLLING
   ==================================================================== */
let pollTimers={},pollActive=true;

async function update(){
  const data=await api('/api/summary');if(!data){document.getElementById('status-bar').textContent='API unreachable';updateStaleUI();return;}
  lastUpdateTs=Date.now();updateStaleUI();
  const count=(data.crypto||[]).length;const now=new Date();
  document.getElementById('status-bar').textContent=count+' tracked'+(activeSource?' · '+activeSource.name:'')+' · '+Object.keys(allMarkets).length+' markets · '+now.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
  const fg=data.fear_greed;updateFG(fg,fg>=75?'EXTREME GREED':fg>=55?'GREED':fg>=45?'NEUTRAL':fg>=25?'FEAR':'EXTREME FEAR');
  lastCryptoData=data.crypto||[];
  renderTracked(data);
  if(firstLoad&&lastCryptoData.length>0){firstLoad=false;selectAsset(selectedAsset||lastCryptoData[0].symbol);}
}

async function updateSlow(){
  const [sr,ar]=await Promise.all([api('/api/signals'),api('/api/accuracy')]);
  renderSignals(sr&&sr.signals?sr.signals:[],ar&&ar.accuracy?ar.accuracy:{});
  const dr=await api('/api/db-stats');renderDBStats(dr&&dr.stats?dr.stats:null);
}

async function updateFeed(){
  const [nr,wr,cr]=await Promise.all([api('/api/news'),api('/api/whale'),api('/api/calendar')]);
  renderNews(nr&&nr.news?nr.news:[]);renderWhale(wr&&wr.transactions?wr.transactions:[]);renderCalendar(cr&&cr.events?cr.events:[]);
}

function startPolling(){update();updateSlow();updateFeed();pollTimers.f=setInterval(()=>{if(pollActive)update();},30000);pollTimers.s=setInterval(()=>{if(pollActive)updateSlow();},60000);pollTimers.d=setInterval(()=>{if(pollActive)updateFeed();},300000);pollTimers.st=setInterval(updateStaleUI,30000);}

document.addEventListener('visibilitychange',()=>{pollActive=!document.hidden;if(pollActive){update();updateSlow();if(ws&&ws.readyState!==1&&ws.readyState!==0)wsConnect();}});

/* ====================================================================
   §19  INIT
   ==================================================================== */
async function init(){
  if(DEBUG)renderDebug();
  dbg('Starting...');
  await probeSource();
  if(activeSource){wsConnect();updateBadge();loadAllMarkets();}else{updateBadge();}
  startPolling();
  // Throttled market re-render from live tickers
  setInterval(()=>{if(document.getElementById('markets-list'))renderMarkets();},2000);
}
init();
