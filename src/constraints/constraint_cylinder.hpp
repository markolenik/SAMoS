/* *************************************************************
 *  
 *   Active Particles on Curved Spaces (APCS)
 *   
 *   Author: Rastko Sknepnek
 *  
 *   Division of Physics
 *   School of Engineering, Physics and Mathematics
 *   University of Dundee
 *   
 *   (c) 2013, 2014
 *   
 *   This program cannot be used, copied, or modified without
 *   explicit permission of the author.
 * 
 * ************************************************************* */

/*!
 * \file constraint_cylinder.hpp
 * \author Rastko Sknepnek, sknepnek@gmail.com
 * \date 10-Oct-2014
 * \brief Declaration of ConstraintCylinder class.
 */ 

#ifndef __CONSTRAINT_CYLINDER_HPP__
#define __CONSTRAINT_CYLINDER_HPP__

#include <cmath>

#include "system.hpp"
#include "parse_parameters.hpp"
#include "constraint.hpp"


using std::sqrt;
using std::sin;
using std::cos;

/*! Enforces all particles to be on the surface of a cylinder of radius 
 *  R along z axis passing through its centre. All velocities will point
 *  in the tangent direction.
*/
class ConstraintCylinder : public Constraint
{
public:
  
  //! Constructor
  //! \param id unique constraint id
  //! \param sys pointer to the system object
  //! \param msg Pointer to the internal state messenger
  //! \param param parameters that define the manifolds (e.g., sphere radius)
  ConstraintCylinder(SystemPtr sys, MessengerPtr msg, pairs_type& param) : Constraint(sys,msg,param)
  { 
    if (param.find("r") == param.end())
    {
      m_msg->msg(Messenger::WARNING,"Cylindrical constraint. No radius set. Assuming 1.");
      m_r = 1.0;
    }
    else
    {
      m_msg->msg(Messenger::INFO,"Cylindrical constraint. Radius set to "+param["r"]+".");
      m_r = lexical_cast<double>(param["r"]);
    }
  }
  
  //! Enforce constraint
  void enforce(Particle&);
  
  //! Rotate director around normal vector to the sphere
  void rotate_director(Particle&, double);
  
  //! Rotate velocity around normal vector to the sphere
  void rotate_velocity(Particle&, double);
  
  //! Project torque onto normal vector onto the sphere and return rotation angle change
  double project_torque(Particle&);
    
private:
  
  double m_r;     //!< Radius of the confining cylinder
  
};

typedef shared_ptr<ConstraintCylinder> ConstraintCylinderPtr;  //!< Shared pointer to the Constraint object

#endif