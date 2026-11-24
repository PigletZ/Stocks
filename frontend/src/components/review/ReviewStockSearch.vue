<template>
  <div class="stock-search">
    <input :value="text" :disabled="disabled" role="combobox" aria-label="搜索关注股票" :aria-expanded="open" aria-controls="review-stock-options" autocomplete="off" placeholder="输入股票名称或代码" @input="input" @focus="search" @blur="blur" @keydown.down.prevent="active=Math.min(active+1,items.length-1)" @keydown.up.prevent="active=Math.max(active-1,0)" @keydown.enter.prevent="chooseActive" @keydown.esc="open=false" />
    <div v-if="open" id="review-stock-options" class="options" role="listbox"><p v-if="loading">正在搜索…</p><p v-else-if="error">{{ error }}</p><p v-else-if="!items.length">没有匹配股票，可输入完整六位代码。</p><button v-for="(stock,index) in items" :key="stock.code" type="button" role="option" :aria-selected="active===index" :class="{active:active===index}" @mousedown.prevent="choose(stock)">{{ stock.name }} <span>{{ stock.code }} · {{ stock.industry||stock.exchange }}</span></button></div>
    <small v-if="modelValue">已选代码 {{ modelValue }}</small>
  </div>
</template>
<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { fetchStockList } from '../../api/client'
import type { PaginatedStockList, StockListItem } from '../../api/client'
import { createLatestLoader } from '../../utils/latestLoader'
const props=defineProps<{modelValue:string;disabled?:boolean}>()
const emit=defineEmits<{'update:modelValue':[value:string]}>()
const text=ref(''),items=ref<StockListItem[]>([]),open=ref(false),loading=ref(false),active=ref(0),error=ref('')
let timer:ReturnType<typeof setTimeout>|undefined,blurTimer:ReturnType<typeof setTimeout>|undefined,emitted=''
const loader=createLatestLoader<PaginatedStockList>({resolve:value=>{items.value=value.items;active.value=0},reject:()=>error.value='搜索暂不可用，可输入完整代码。',pending:value=>loading.value=value})
function update(value:string){emitted=value;emit('update:modelValue',value)}
function input(event:Event){text.value=(event.target as HTMLInputElement).value;update(/^\d{6}$/.test(text.value.trim())?text.value.trim():'');search()}
function search(){if(timer)clearTimeout(timer);if(blurTimer)clearTimeout(blurTimer);loader.cancel();items.value=[];error.value='';const value=text.value.trim();open.value=!!value;if(!value||props.disabled)return;loading.value=true;timer=setTimeout(()=>loader.load(signal=>fetchStockList(value,undefined,1,8,'code','asc',signal)),250)}
function choose(stock:StockListItem){if(timer)clearTimeout(timer);loader.cancel();text.value=stock.name+' '+stock.code;open.value=false;items.value=[];update(stock.code)}
function chooseActive(){if(open.value&&items.value[active.value])choose(items.value[active.value])}
function blur(){blurTimer=setTimeout(()=>open.value=false,140)}
watch(()=>props.modelValue,value=>{if(value!==emitted){text.value=value;items.value=[];open.value=false;loader.cancel()}},{immediate:true})
onUnmounted(()=>{loader.dispose();if(timer)clearTimeout(timer);if(blurTimer)clearTimeout(blurTimer)})
</script>
<style scoped>
.stock-search{position:relative;min-width:240px}.stock-search>input{width:100%;box-sizing:border-box;padding:10px 12px;background:#0d1727;border:1px solid #3a4a60;border-radius:7px;color:#e5e7eb;font-size:13px}.stock-search small{display:block;font-size:11px;color:#93a4ba;margin-top:5px}.options{position:absolute;z-index:8;top:42px;left:0;right:0;background:#152135;border:1px solid #42516b;border-radius:8px;box-shadow:0 12px 24px #0005;overflow:hidden}.options button{display:block;text-align:left;width:100%;background:transparent;border:0;color:#e5e7eb;padding:11px 12px;cursor:pointer;font-size:13px}.options button:hover,.options button.active{background:#243b59}.options span{display:block;color:#9ca3af;font-size:11px;margin-top:4px}.options p{font-size:12px;line-height:1.8;color:#9ca3af;padding:8px 12px}
</style>
