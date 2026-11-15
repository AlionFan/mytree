'use strict';
(() => {
 const face=`<svg class="sapling-character" viewBox="0 0 100 104" fill="none" aria-hidden="true"><path class="sapling-leaves" d="M50 38C26 39 14 24 19 9c20-2 34 8 31 29Zm0-3C48 14 62 4 82 8c2 20-11 32-32 27Z" fill="#72cd68" stroke="#244f38" stroke-width="2.8" stroke-linejoin="round"/><path d="M50 26v22" stroke="#244f38" stroke-width="3.3" stroke-linecap="round"/><rect x="20" y="36" width="62" height="61" rx="25" fill="#32c970"/><path d="M29 43c-5 12-5 29 1 39" stroke="#8eeaa0" stroke-width="3" stroke-linecap="round"/><g class="sapling-eyes" fill="#173a2a"><ellipse cx="42" cy="61" rx="3.2" ry="4.2"/><ellipse cx="61" cy="61" rx="3.2" ry="4.2"/></g><path d="M45 74q7 6 14-1" stroke="#173a2a" stroke-width="2.7" stroke-linecap="round"/><ellipse cx="32" cy="70" rx="4.8" ry="2.7" fill="#99e590"/><ellipse cx="72" cy="70" rx="4.8" ry="2.7" fill="#99e590"/></svg>`;
 window.MytreeCharacter=()=>face;
 document.querySelectorAll('.auth-mascot,.brand-mark,[data-character]').forEach(el=>el.innerHTML=face);
 const pause=()=>document.documentElement.classList.toggle('page-background',document.hidden);
 document.addEventListener('visibilitychange',pause);pause();
})();
