import Header from './Header'
import { Outlet } from 'react-router-dom'
import Footer from './Footer'
function AppLayout() {
  return (
    <div>
    <Header></Header>
    <Outlet/>
    <Footer/>
      </div>
  )
}

export default AppLayout