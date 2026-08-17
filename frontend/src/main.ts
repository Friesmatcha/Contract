import { ElConfigProvider } from 'element-plus'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-config-provider.css'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './styles.css'

createApp(App).component('ElConfigProvider', ElConfigProvider).use(router).mount('#app')
