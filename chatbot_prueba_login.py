import streamlit as st
import streamlit_authenticator as stauth

def authenticator_login():
    import yaml
    from yaml.loader import SafeLoader
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)


    # Pre-hashing all plain text passwords once
    #stauth.Hasher.hash_passwords(config['credentials'])

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days']
    )


    authenticator.login(single_session=True, fields={ 'Form name':'Chatbot Procesos-UFM', 'Username':'Nombre de usuario', 'Password':'Contraseña', 'Login':'Login', 'Captcha':'Captcha'})

    if st.session_state["authentication_status"]:
        authenticator.logout()
        st.write(f'Welcome *{st.session_state["name"]}*')
        st.write(f'{st.session_state}')
        #st.write(f'Welcome *{st.session_state["id_usar"]}*')

        st.title('Chatbot')
        # enter the rest of the streamlit app here
    elif st.session_state["authentication_status"] is False:
        st.error('Nombre de usuario / Contraseña es incorrecta')
    elif st.session_state["authentication_status"] is None:
        st.warning('Por favor introduzca su nombre de usuario y contraseña')




if __name__ == "__main__":
    authenticator_login()