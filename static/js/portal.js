(function(){
 const app=document.querySelector('.rno-app');
 const body=document.body;
 const btn=document.querySelector('[data-sidebar-toggle]');
 if(!app||!btn)return;
 const dashboard=body.classList.contains('rno-dashboard-page');
 const key='rno.sidebar.choice.v44';
 const saved=localStorage.getItem(key);
 if(dashboard){
   if(saved==='full')body.classList.add('sidebar-full');
 }else if(saved==='mini'){
   app.classList.add('sidebar-mini');
 }
 btn.addEventListener('click',function(){
   if(dashboard){
     body.classList.toggle('sidebar-full');
     localStorage.setItem(key,body.classList.contains('sidebar-full')?'full':'mini');
   }else{
     app.classList.toggle('sidebar-mini');
     localStorage.setItem(key,app.classList.contains('sidebar-mini')?'mini':'full');
   }
 });
})();
