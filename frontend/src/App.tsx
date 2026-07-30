import { Toaster } from 'react-hot-toast'
import './App.css'
import { Provider } from 'react-redux'
import store from './Store/store'
import { RouterProvider } from 'react-router-dom'
import { router } from './router/router'

function App() {

  return (
    <>
      <Provider store={store}>
      <RouterProvider router={router}/>
      <Toaster/>
      </Provider>
    </>
  )
}

export default App
